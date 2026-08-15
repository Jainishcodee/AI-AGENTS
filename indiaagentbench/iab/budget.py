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
import os
import time

from .providers import ProviderError, QuotaDead, RateLimited, Transient, build


class AllEndpointsDead(Exception):
    """Every host for this model is out of quota. Resume the run later."""


class Rotator:
    """Holds the live endpoint for one model under test.

    Free tiers cap requests *per minute* as well as per day, and a trajectory
    fires 4-6 requests back to back. Reactive backoff alone cannot clear a
    per-minute window -- it just burns the retry budget and retires a healthy
    endpoint. So the rotator paces proactively: it keeps a minimum interval
    between requests and widens it whenever a 429 says the current pace is too
    fast. Slower and finishing beats faster and stalling.
    """

    MAX_BACKOFF = 90.0
    MAX_INTERVAL = 30.0

    def __init__(self, model_name, endpoints, log=print, min_interval=None):
        self.model_name = model_name
        self.specs = list(endpoints)
        self.log = log
        self.i = 0
        self.dead = set()
        self._provider = None
        self._cooldown_until = 0.0
        # Default pacing from the environment so a run can be slowed down
        # without a code change when a provider tightens its limits.
        self.min_interval = (min_interval if min_interval is not None
                             else float(os.environ.get("IAB_MIN_INTERVAL", "1.0")))
        self._last_call = 0.0

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

    def _pace(self):
        """Hold the minimum gap since the last request, plus any cooldown."""
        now = time.time()
        until = max(self._last_call + self.min_interval, self._cooldown_until)
        if until > now:
            time.sleep(until - now)
        self._last_call = time.time()

    def _slow_down(self):
        """A 429 means the current pace is too fast. Widen it for good."""
        was = self.min_interval
        self.min_interval = min(max(self.min_interval * 2, 4.0), self.MAX_INTERVAL)
        if self.min_interval > was:
            self.log(f"    . {self.model_name} pacing {was:.0f}s -> "
                     f"{self.min_interval:.0f}s between requests")

    def chat(self, system, messages, tools, attempts_per_endpoint=6):
        """One model turn: back off on throttling, then fail over, then give up.

        The retry budget is *per endpoint*, not per call. An earlier version
        spent all its attempts on a single throttled host and then raised --
        never touching a healthy fallback that still had quota, which stalled a
        run three tasks in. Persistent throttling is indistinguishable from
        exhaustion from the outside, so after a few refusals the right move is
        to move on rather than keep asking.
        """
        last = None
        while True:
            p = self.provider()          # raises AllEndpointsDead when none remain
            backoff = 2.0
            for _ in range(attempts_per_endpoint):
                self._pace()
                try:
                    return p.chat(system, messages, tools)
                except (RateLimited, Transient) as e:
                    # "This host is fine, just wait" -- a dropped TCP connection
                    # must not cost an endpoint. Long free-tier runs drop
                    # connections routinely.
                    last = e
                    if isinstance(e, RateLimited):
                        self._slow_down()
                    delay = min(getattr(e, "retry_after", None) or backoff, self.MAX_BACKOFF)
                    self._cooldown_until = time.time() + delay
                    backoff = min(backoff * 2, self.MAX_BACKOFF)
                except QuotaDead as e:
                    last = e
                    self._next("daily quota exhausted")
                    break
                except ProviderError as e:
                    last = e
                    self._next(f"error: {e}")
                    break
            else:
                self._next(f"still throttled after {attempts_per_endpoint} attempts")
