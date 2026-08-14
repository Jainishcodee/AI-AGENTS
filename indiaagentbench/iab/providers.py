"""Model providers, normalised to one tool-calling interface.

Every provider returns the same shape:

    {"text": str, "tool_calls": [{"id": str, "name": str, "args": dict}], "model": str}

and accepts history in one internal format, which each provider translates to
its own wire format:

    {"role": "user",      "content": str}
    {"role": "assistant", "content": str, "tool_calls": [...as above...]}
    {"role": "tool",      "tool_call_id": str, "name": str, "content": str}

The translation is the whole point of this module. OpenAI-compatible APIs need
assistant tool calls as {id, type, function:{name, arguments}} with `arguments`
as a JSON *string*, and every tool result must carry a matching `tool_call_id`;
Gemini needs functionCall/functionResponse parts and no ids at all. Forwarding
the internal format straight to either one fails on the first tool result --
which is exactly the bug this module was rewritten to fix, and which the mock
provider hid because it ignores history entirely.

Two failure modes are distinguished, and the distinction matters more than it
looks: `RateLimited` means back off and retry the same endpoint, `QuotaDead`
means this endpoint is finished for the day and the rotator should stop asking.
Conflating them either burns the run in a retry loop or discards capacity that
was only briefly throttled.
"""
import json
import os
import time

import requests

from .common import load_env

load_env()   # keys from indiaagentbench/.env; real env vars still win


class ProviderError(Exception):
    pass


class RateLimited(ProviderError):
    """Transient: retry after a backoff."""

    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


class QuotaDead(ProviderError):
    """Terminal for today: daily allowance is gone."""


class Transient(ProviderError):
    """Network blip: retry the same endpoint. Not the endpoint's fault.

    Long free-tier runs drop connections. Treating that as an endpoint failure
    would burn through healthy hosts over a momentary TCP reset.
    """


def _post(url, **kw):
    """requests.post with network faults mapped into the retry taxonomy."""
    try:
        return requests.post(url, **kw)
    except requests.exceptions.RequestException as e:
        raise Transient(f"{type(e).__name__}: {str(e)[:200]}") from e


class Provider:
    name = "base"

    def __init__(self, model, api_key=None, base_url=None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def chat(self, system, messages, tools):
        raise NotImplementedError


# --------------------------------------------------------------------------


class OpenAICompat(Provider):
    """Groq, Cerebras, OpenRouter, Sarvam, Together -- all speak this dialect."""

    name = "openai-compat"

    def payload(self, system, messages, tools):
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + to_openai(messages),
            "tools": [{"type": "function",
                       "function": {"name": t["name"], "description": t["description"],
                                    "parameters": t["input_schema"]}}
                      for t in tools],
            "temperature": 0,
        }

    def chat(self, system, messages, tools):
        r = _post(f"{self.base_url}/chat/completions",
                  headers={"Authorization": f"Bearer {self.api_key}"},
                  json=self.payload(system, messages, tools), timeout=120)
        self._raise_for_limits(r)
        if r.status_code >= 400:
            raise ProviderError(f"{self.model} HTTP {r.status_code}: {r.text[:400]}")

        msg = r.json()["choices"][0]["message"]
        calls = []
        for n, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            calls.append({"id": tc.get("id") or f"call_{n}",
                          "name": fn.get("name", ""),
                          "args": _loads(fn.get("arguments"))})
        return {"text": msg.get("content") or "", "tool_calls": calls, "model": self.model}

    @staticmethod
    def _raise_for_limits(r):
        if r.status_code != 429:
            return
        body = r.text.lower()
        if "daily" in body or "quota" in body or "tpd" in body or "rpd" in body:
            raise QuotaDead(r.text[:300])
        raise RateLimited(r.text[:300], retry_after=_retry_after(r))


class Gemini(Provider):
    """Free tier has per-model daily caps that are small and hit fast."""

    name = "gemini"
    ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

    def payload(self, system, messages, tools):
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": to_gemini(messages),
            "tools": [{"functionDeclarations": [_declare(t) for t in tools]}],
            "generationConfig": {"temperature": 0},
        }

    def chat(self, system, messages, tools):
        r = _post(f"{self.ROOT}/{self.model}:generateContent",
                  headers={"x-goog-api-key": self.api_key},
                  json=self.payload(system, messages, tools), timeout=120)
        if r.status_code == 429:
            body = r.text.lower()
            if "perday" in body.replace("_", "") or "daily" in body:
                raise QuotaDead(r.text[:300])
            raise RateLimited(r.text[:300], retry_after=_retry_after(r))
        if r.status_code >= 400:
            raise ProviderError(f"{self.model} HTTP {r.status_code}: {r.text[:400]}")

        cands = r.json().get("candidates") or [{}]
        parts = cands[0].get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts)
        # Gemini has no tool-call ids, so synthesise stable ones. The runner
        # needs them to pair results back to calls in the internal format.
        calls = [{"id": f"call_{n}",
                  "name": p["functionCall"]["name"],
                  "args": dict(p["functionCall"].get("args") or {})}
                 for n, p in enumerate(p for p in parts if "functionCall" in p)]
        return {"text": text, "tool_calls": calls, "model": self.model}


class Mock(Provider):
    """Scripted provider for testing the harness without spending a single token.

    Takes a list of turns, each either a list of tool calls or a final string.
    The whole runner -- loop control, verification, resumption, survival
    logging -- is exercised offline before any real quota is touched.
    """

    name = "mock"

    def __init__(self, model="mock", script=None):
        super().__init__(model)
        self.script = list(script or [])
        self.i = 0

    def chat(self, system, messages, tools):
        # Record what the runner handed us so tests can assert on history shape.
        # The mock ignoring `messages` is precisely how a broken wire format
        # survived 53 green tests once already.
        self.seen = list(messages)
        if self.i >= len(self.script):
            return {"text": "done", "tool_calls": [], "model": self.model}
        turn = self.script[self.i]
        self.i += 1
        if isinstance(turn, str):
            return {"text": turn, "tool_calls": [], "model": self.model}
        calls = [{"id": tc.get("id") or f"call_{self.i}_{n}", **tc}
                 for n, tc in enumerate(turn)]
        return {"text": "", "tool_calls": calls, "model": self.model}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _loads(s):
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s or "{}")
    except (ValueError, TypeError):
        # A model that emits malformed tool arguments is producing a slot error,
        # which is data for the H2 analysis -- surface it, do not crash the run.
        return {"__unparsed__": s}


def _retry_after(r):
    try:
        return float(r.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


def to_openai(messages):
    """Internal format -> OpenAI chat-completions wire format.

    Two things here are mandatory rather than cosmetic: `arguments` must be a
    JSON *string*, not an object, and every tool message must carry the
    `tool_call_id` of the call it answers. Omitting either produces a 400 on the
    first tool result -- which is every task in this benchmark.
    """
    out = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            out.append({"role": "tool",
                        "tool_call_id": m["tool_call_id"],
                        "name": m.get("name", ""),
                        "content": m["content"]})
        elif role == "assistant":
            msg = {"role": "assistant", "content": m.get("content") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                    for tc in m["tool_calls"]]
            out.append(msg)
        else:
            out.append({"role": "user", "content": m["content"]})
    return out


def _strip_schema(schema):
    """Gemini rejects several JSON Schema keywords that the others accept."""
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items()
           if k not in ("additionalProperties", "$schema", "default")}
    if "properties" in out:
        out["properties"] = {k: _strip_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _strip_schema(out["items"])
    return out


def _declare(tool):
    """Gemini function declaration. Omits `parameters` for no-argument tools.

    An object schema with an empty `properties` map is rejected, and several
    tools here (current_time, list_schemes) genuinely take no arguments.
    """
    d = {"name": tool["name"], "description": tool["description"]}
    schema = _strip_schema(tool["input_schema"])
    if schema.get("properties"):
        d["parameters"] = schema
    return d


def to_gemini(messages):
    """Internal format -> Gemini contents.

    Gemini pairs a functionResponse to its call by name rather than by id, and
    expects all responses to one model turn grouped into a single user content.
    Emitting them as separate contents breaks parallel tool calls.
    """
    out = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            part = {"functionResponse": {"name": m.get("name", "tool"),
                                         "response": {"result": m["content"]}}}
            prev = out[-1] if out else None
            if prev and prev["role"] == "user" and "functionResponse" in prev["parts"][0]:
                prev["parts"].append(part)
            else:
                out.append({"role": "user", "parts": [part]})
        elif role == "assistant":
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m.get("tool_calls") or []:
                parts.append({"functionCall": {"name": tc["name"], "args": tc["args"]}})
            out.append({"role": "model", "parts": parts or [{"text": ""}]})
        else:
            out.append({"role": "user", "parts": [{"text": m["content"]}]})
    return out


# --------------------------------------------------------------------------
# endpoint registry
# --------------------------------------------------------------------------

# One model under test may be reachable through several hosts. Rotation happens
# across the hosts of a *single* model -- never across different models, since
# the model is the thing being measured and substituting one for another would
# quietly corrupt the comparison. This is the key difference from the reelflow
# rotator it grew out of, where any model that answered was acceptable.
#   verified 2026-08-03:
#   - sarvam-30b and sarvam-m are BOTH deprecated upstream. sarvam-105b is the
#     live Sarvam chat model, on their own /v1. Groq does not host any Sarvam
#     model -- it serves 11 open-weight Llama/gpt-oss/Qwen models.
#   - BharatGen Param2 is bharatgenai/Param2-17B-A2.4B-Thinking on HuggingFace,
#     tool calling supported, reachable via HF Inference Providers. Not on
#     OpenRouter.
#   Model IDs marked UNCONFIRMED still need a live 1-call check before a full
#   run; `python -m iab.check_endpoints` does exactly that.
ENDPOINTS = {
    "sarvam-105b": [
        ("openai-compat", "https://api.sarvam.ai/v1", "SARVAM_API_KEY", "sarvam-105b"),
    ],
    "param2-17b": [
        ("openai-compat", "https://router.huggingface.co/v1", "HF_TOKEN",
         "bharatgenai/Param2-17B-A2.4B-Thinking"),   # UNCONFIRMED routing
    ],
    "gemini-flash": [
        ("gemini", None, "GEMINI_API_KEY", "gemini-2.5-flash"),
        ("gemini", None, "GEMINI_API_KEY", "gemini-3.5-flash"),
    ],
    "llama-70b": [
        ("openai-compat", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
         "llama-3.3-70b-versatile"),
        ("openai-compat", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY",
         "llama-3.3-70b"),                            # UNCONFIRMED id
    ],
}

CLASSES = {"openai-compat": OpenAICompat, "gemini": Gemini}


def build(kind, base_url, key_env, model_id):
    key = os.environ.get(key_env)
    if not key:
        raise ProviderError(f"missing {key_env}")
    return CLASSES[kind](model_id, api_key=key, base_url=base_url)


def sleep(seconds):
    time.sleep(seconds)
