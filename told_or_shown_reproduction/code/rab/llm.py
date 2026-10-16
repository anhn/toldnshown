"""Minimal, dependency-light clients for chat models with tool calling.

Two API styles are supported:
  - "openai":    any OpenAI-compatible /chat/completions endpoint (OpenAI, Azure OpenAI,
                 OpenRouter, Together, Groq, DeepSeek, Mistral, vLLM, Ollama, LM Studio, ...)
  - "anthropic": the Anthropic Messages API
A model is described by a dict from config.json, e.g.
  {"api": "openai", "model": "gpt-4.1", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
"""
import json, os, time
import requests


class LLMError(RuntimeError):
    pass


def _post(url, headers, body, timeout=600, retries=5):
    delay = 5
    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise LLMError(str(e))
            time.sleep(delay); delay *= 2; continue
        if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < retries - 1:
            time.sleep(delay); delay *= 2; continue
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()


class Chat:
    """Provider-neutral conversation with tool use.

    tools: list of {"name", "description", "parameters" (JSON schema)}
    step() returns (text, tool_calls) where tool_calls = [{"id", "name", "args"}]
    add_tool_results([(id, output_str), ...]) appends results for the last calls.
    """

    def __init__(self, spec, system, tools=None, max_tokens=8192, temperature=None):
        self.spec = spec
        self.api = spec.get("api", "openai")
        self.model = spec["model"]
        key_env = spec.get("api_key_env")
        self.key = os.environ.get(key_env, "") if key_env else spec.get("api_key", "")
        self.system = system
        self.tools = tools or []
        self.max_tokens = spec.get("max_tokens", max_tokens)
        self.temperature = spec.get("temperature", temperature)
        self.messages = []
        self.usage = {"input": 0, "output": 0, "calls": 0}
        if self.api == "openai":
            self.messages.append({"role": "system", "content": system})

    # ---------------------------------------------------------------- API calls
    def _call(self):
        self.usage["calls"] += 1
        if self.api == "openai":
            base = self.spec.get("base_url", "https://api.openai.com/v1").rstrip("/")
            body = {"model": self.model, "messages": self.messages}
            tok_field = self.spec.get("max_tokens_field", "max_tokens")
            body[tok_field] = self.max_tokens
            if self.temperature is not None:
                body["temperature"] = self.temperature
            if self.tools:
                body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                                     "parameters": t["parameters"]}} for t in self.tools]
            body.update(self.spec.get("extra_body", {}))
            headers = {"Content-Type": "application/json"}
            if self.key:
                headers["Authorization"] = f"Bearer {self.key}"
            headers.update(self.spec.get("extra_headers", {}))
            out = _post(base + "/chat/completions", headers, body)
            u = out.get("usage") or {}
            self.usage["input"] += u.get("prompt_tokens", 0); self.usage["output"] += u.get("completion_tokens", 0)
            msg = out["choices"][0]["message"]
            keep = {"role": "assistant", "content": msg.get("content") or ""}
            calls = []
            for tc in msg.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {"__unparsed__": tc["function"].get("arguments")}
                calls.append({"id": tc["id"], "name": tc["function"]["name"], "args": args})
            if msg.get("tool_calls"):
                keep["tool_calls"] = msg["tool_calls"]
            self.messages.append(keep)
            return msg.get("content") or "", calls
        elif self.api == "anthropic":
            base = self.spec.get("base_url", "https://api.anthropic.com").rstrip("/")
            body = {"model": self.model, "max_tokens": self.max_tokens, "system": self.system, "messages": self.messages}
            if self.temperature is not None:
                body["temperature"] = self.temperature
            if self.tools:
                body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                                 for t in self.tools]
            body.update(self.spec.get("extra_body", {}))
            headers = {"Content-Type": "application/json", "x-api-key": self.key,
                       "anthropic-version": self.spec.get("anthropic_version", "2023-06-01")}
            headers.update(self.spec.get("extra_headers", {}))
            out = _post(base + "/v1/messages", headers, body)
            u = out.get("usage") or {}
            self.usage["input"] += u.get("input_tokens", 0); self.usage["output"] += u.get("output_tokens", 0)
            content = out.get("content", [])
            self.messages.append({"role": "assistant", "content": content})
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            calls = [{"id": b["id"], "name": b["name"], "args": b.get("input", {})} for b in content if b.get("type") == "tool_use"]
            return text, calls
        raise LLMError(f"unknown api style {self.api}")

    # ---------------------------------------------------------------- public
    def user(self, text):
        self.messages.append({"role": "user", "content": text})

    def step(self):
        return self._call()

    def add_tool_results(self, results):
        if self.api == "openai":
            for cid, out in results:
                self.messages.append({"role": "tool", "tool_call_id": cid, "content": out})
        else:
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": cid, "content": out} for cid, out in results]})


def complete(spec, system, user, max_tokens=2048):
    """One-shot completion without tools (used by the judge)."""
    c = Chat(spec, system, tools=None, max_tokens=max_tokens, temperature=spec.get("temperature", 0))
    c.user(user)
    text, _ = c.step()
    return text, c.usage
