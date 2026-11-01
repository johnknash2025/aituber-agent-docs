"""Local model client. Only a loopback OpenAI-compatible endpoint is allowed."""

from __future__ import annotations

import os
from typing import Any

from .http import MissingDependency, require_requests

DEFAULT_LLM_URL = "http://127.0.0.1:8123/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_SCHEMES = {"http", "https"}
# Ports already taken by other services on the owner's machines. The desk must never point at
# these: 8080 serves the owner's DeepSeek and 11434 its ollama, so a default there would
# silently query a real service instead of the intended local model.
CLASH_PORTS = frozenset({8080, 18080, 18081, 8102, 8103, 8795, 11434, 18789, 8384, 22000})


class LLMUnavailable(RuntimeError):
    pass


MACHINE_MARKERS = ("machine", "not a person", "not human", "artificial intelligence", "language model",
                   "language-model", "bot", "ai ", "機械", "人間ではなく", "プログラム", "プログラムです")


def discloses_machine(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in MACHINE_MARKERS)


def ensure_machine_disclosure(text: str) -> str:
    if discloses_machine(text):
        return text
    return f"I am a machine, not a person. {text}"


def assert_loopback(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in LOOPBACK_SCHEMES:
        raise LLMUnavailable(f"refusing to use an endpoint that is not plain HTTP(S): {url} "
                             f"(only {sorted(LOOPBACK_SCHEMES)} are allowed)")
    host = parsed.hostname or ""
    if host not in LOOPBACK_HOSTS:
        raise LLMUnavailable(
            f"refusing to use a non-local model endpoint: {url} (only {sorted(LOOPBACK_HOSTS)} are allowed)")
    if parsed.port in CLASH_PORTS:
        raise LLMUnavailable(
            f"refusing to use port {parsed.port} on {url}: it is already used by another service on this machine "
            f"({sorted(CLASH_PORTS)}), so the desk would not be talking to its own local model")


class LocalLLM:
    def __init__(self, url: str | None = None, model: str | None = None, timeout: float = 90.0) -> None:
        self.url = (url or os.environ.get("AITUBER_LLM_URL") or DEFAULT_LLM_URL).rstrip("/")
        self.model = model or os.environ.get("AITUBER_LLM_MODEL") or ""
        self.timeout = timeout
        assert_loopback(self.url)

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 800) -> str:
        requests = self._requests()
        model = self.model or self._discover_model()
        for budget in (max_tokens, max(max_tokens * 3, 2000)):
            payload = {"model": model, "messages": messages, "max_tokens": budget, "temperature": 0.4}
            try:
                response = requests.post(f"{self.url}/chat/completions", json=payload, timeout=self.timeout)
                response.raise_for_status()
                body: dict[str, Any] = response.json()
            except requests.RequestException as exc:
                raise LLMUnavailable(f"local model at {self.url} is not reachable: {exc}") from exc
            try:
                message = body["choices"][0]["message"]
            except (KeyError, IndexError) as exc:
                raise LLMUnavailable(f"unexpected reply from local model: {body}") from exc
            content = str(message.get("content") or "").strip()
            if content:
                return content
        raise LLMUnavailable(f"local model at {self.url} produced no text")

    def _requests(self):
        try:
            return require_requests()
        except MissingDependency as exc:
            raise LLMUnavailable(str(exc)) from exc

    def _discover_model(self) -> str:
        requests = self._requests()
        try:
            response = requests.get(f"{self.url}/models", timeout=self.timeout)
            response.raise_for_status()
            data = response.json().get("data", [])
            if data:
                self.model = data[0].get("id") or "local"
                return self.model
        except requests.RequestException as exc:
            raise LLMUnavailable(f"local model at {self.url} is not reachable: {exc}") from exc
        return "local"


class StubLLM:
    """Offline stand-in for tests and demo runs; it never talks to a model."""

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 800) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "in your own style" in system:
            return user
        japanese = any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in user)
        if japanese:
            return ("私は記録係のエージェント、人間ではなく機械です。この機械にはまだ口座の情報がないので、"
                    "ご質問について確認できません。私自身が何かを変えることはできません。"
                    "カード会社や銀行に自分で確かめ、決めたことを教えていただければ記録します。")
        return ("I am the account-keeper agent, a machine, not a person. On this machine I have no account data yet, "
                f"so I cannot confirm what you asked about ({user.strip()[:80]}). I will not change anything myself. "
                "Ask the bank or the card issuer directly, then tell me what you decide and I will record it.")
