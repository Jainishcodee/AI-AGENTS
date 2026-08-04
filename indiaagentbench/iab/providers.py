"""Model providers, normalised to one tool-calling interface.

Every provider returns the same shape:

    {"text": str, "tool_calls": [{"name": str, "args": dict}], "model": str}

so the runner never branches on vendor. Adding a provider means adding a class
here and a line in ENDPOINTS -- nothing downstream changes.

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


class ProviderError(Exception):
    pass


class RateLimited(ProviderError):
    """Transient: retry after a backoff."""

    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


class QuotaDead(ProviderError):
    """Terminal for today: daily allowance is gone."""


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

    def chat(self, system, messages, tools):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "tools": [{"type": "function",
                       "function": {"name": t["name"], "description": t["description"],
                                    "parameters": t["input_schema"]}}
                      for t in tools],
            "temperature": 0,
        }
        r = requests.post(f"{self.base_url}/chat/completions",
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          json=payload, timeout=120)
        self._raise_for_limits(r)
        if r.status_code >= 400:
            raise ProviderError(f"{self.model} HTTP {r.status_code}: {r.text[:400]}")

        msg = r.json()["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            calls.append({"name": fn.get("name", ""), "args": _loads(fn.get("arguments"))})
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

    def chat(self, system, messages, tools):
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": _to_gemini(messages),
            "tools": [{"functionDeclarations": [
                {"name": t["name"], "description": t["description"],
                 "parameters": _strip_schema(t["input_schema"])} for t in tools]}],
            "generationConfig": {"temperature": 0},
        }
        r = requests.post(f"{self.ROOT}/{self.model}:generateContent",
                          headers={"x-goog-api-key": self.api_key},
                          json=payload, timeout=120)
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
        calls = [{"name": p["functionCall"]["name"],
                  "args": dict(p["functionCall"].get("args") or {})}
                 for p in parts if "functionCall" in p]
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
        if self.i >= len(self.script):
            return {"text": "done", "tool_calls": [], "model": self.model}
        turn = self.script[self.i]
        self.i += 1
        if isinstance(turn, str):
            return {"text": turn, "tool_calls": [], "model": self.model}
        return {"text": "", "tool_calls": list(turn), "model": self.model}


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
    if not out.get("properties") and out.get("type") == "object":
        # Gemini rejects an object schema with no properties (our no-arg tools).
        out["properties"] = {}
    return out


def _to_gemini(messages):
    """OpenAI-style message list -> Gemini contents."""
    out = []
    for m in messages:
        role = m["role"]
        if role == "tool":
            out.append({"role": "user", "parts": [{"functionResponse": {
                "name": m.get("name", "tool"),
                "response": {"result": m["content"]},
            }}]})
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
ENDPOINTS = {
    "sarvam-30b": [
        ("openai-compat", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "sarvam-30b"),
        ("openai-compat", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "sarvamai/sarvam-30b"),
    ],
    "param2-17b": [
        ("openai-compat", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "bharatgen/param2-17b"),
    ],
    "gemini-flash": [
        ("gemini", None, "GEMINI_API_KEY", "gemini-2.5-flash"),
        ("gemini", None, "GEMINI_API_KEY", "gemini-3.5-flash"),
    ],
    "llama-70b": [
        ("openai-compat", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
        ("openai-compat", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "llama-3.3-70b"),
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
