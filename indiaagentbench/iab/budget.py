"""Endpoint rotation for running a fixed model set on free tiers.

Descended from the quota rotator in reelflow's distill.py, with one crucial
change. There, rotation moved across *different models* -- any model that
answered was fine, because the job was extraction. Here the model is the
independent variable, so substituting one for another would silently destroy
the comparison. Rotation therefore only ever moves between hosts serving the
*same* weights.

When every host for a model is exhausted, the correct behaviour is to stop, not
to degrade: the run pauses and resumes tomorrow against the same cache. That is
why resumability is a hard requirement of this design rather than a convenience.
"""
import time

from .providers import ProviderError, QuotaDead, RateLimited, Transient, build


class AllEndpointsDead(Exception):
    """Every host for this model is out of quota. Resume the run later."""


class Rotator:
    """Holds the live endpoint for one model under test."""

    MAX_BACKOFF = 60.0

    def __init__(self, model_name, endpoints, log=print):
        self.model_name = model_name
        self.specs = list(endpoints)
        self.log = log
        self.i = 0
        self.dead = set()
        self._provider = None
        self._cooldown_until = 0.0

    def provider(self):
        while self.i < len(self.specs):
            if self.i in self.dead:
                self.i += 1
                continue
            if self._provider is None:
                try:
                    self._provider = build(*self.specs[self.i])
                except ProviderError as e:
                    self.log(f"    ! {self.model_name} endpoint {self.i} unavailable: {e}")
                    self.dead.add(self.i)
                    self.i += 1
                    continue
            return self._provider
        raise AllEndpointsDead(f"{self.model_name}: no live endpoints")

    def _next(self, why):
        old = self.i
        self.dead.add(old)
        self._provider = None
        self.i += 1
        # Cooldown belongs to the endpoint that earned it. Carrying it across a
        # failover would idle a fresh host for the dead one's backoff.
        self._cooldown_until = 0.0
        if self.i < len(self.specs):
            self.log(f"    ! {self.model_name} endpoint {old} {why} -> falling back to {self.i}")
        else:
            self.log(f"    ! {self.model_name} endpoint {old} {why} -- no hosts left")

    def chat(self, system, messages, tools, attempts=5):
        """One model turn, with backoff on throttling and failover on exhaustion."""
        backoff = 2.0
        last = None
        for _ in range(attempts):
            p = self.provider()
            wait = self._cooldown_until - time.time()
            if wait > 0:
                time.sleep(wait)
            try:
                return p.chat(system, messages, tools)
            except (RateLimited, Transient) as e:
                # Both mean "this host is fine, just wait" -- a dropped TCP
                # connection must not cost an endpoint. Long free-tier runs
                # drop connections routinely.
                last = e
                delay = min(getattr(e, "retry_after", None) or backoff, self.MAX_BACKOFF)
                self._cooldown_until = time.time() + delay
                backoff = min(backoff * 2, self.MAX_BACKOFF)
            except QuotaDead as e:
                last = e
                self._next("daily quota exhausted")
            except ProviderError as e:
                last = e
                self._next(f"error: {e}")
        raise AllEndpointsDead(f"{self.model_name}: gave up after {attempts} attempts ({last})")
