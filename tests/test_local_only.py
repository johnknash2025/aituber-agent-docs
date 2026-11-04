import pytest

from window.llm import DEFAULT_LLM_URL, LLMUnavailable, LocalLLM, assert_loopback
from window.persona import load_personas
from window.llm import StubLLM
from window.tts import PrintTTS
from window.window import Window

from pathlib import Path

PERSONAS = Path(__file__).resolve().parent.parent / "personas"


def test_default_endpoint_is_the_local_model(monkeypatch):
    monkeypatch.delenv("AITUBER_LLM_URL", raising=False)
    assert DEFAULT_LLM_URL == "http://127.0.0.1:8123/v1"
    assert LocalLLM().url == DEFAULT_LLM_URL


def test_a_local_env_override_is_still_honoured(monkeypatch):
    monkeypatch.setenv("AITUBER_LLM_URL", "http://127.0.0.1:8124/v1")
    assert LocalLLM().url == "http://127.0.0.1:8124/v1"


def test_default_endpoint_avoids_the_service_ports_in_use(monkeypatch):
    from window.llm import CLASH_PORTS
    monkeypatch.delenv("AITUBER_LLM_URL", raising=False)
    from urllib.parse import urlparse
    assert urlparse(DEFAULT_LLM_URL).port not in CLASH_PORTS


def test_the_deepseek_and_ollama_ports_are_refused():
    for url in ("http://127.0.0.1:8080/v1", "http://127.0.0.1:11434/v1"):
        with pytest.raises(LLMUnavailable):
            LocalLLM(url=url)


def test_cloud_endpoints_are_refused():
    for url in ("https://api.openai.com/v1", "http://192.168.1.5:11434/v1", "https://example.com/v1"):
        with pytest.raises(LLMUnavailable):
            LocalLLM(url=url)


def test_loopback_variants_are_allowed():
    for url in ("http://localhost:8123/v1", "http://127.0.0.1:8124/v1"):
        assert_loopback(url)


def test_non_http_schemes_are_refused_even_on_loopback():
    for url in ("ftp://localhost/v1", "file://127.0.0.1/tmp/model", "ws://localhost:8080/v1"):
        with pytest.raises(LLMUnavailable):
            assert_loopback(url)
        with pytest.raises(LLMUnavailable):
            LocalLLM(url=url)


def test_an_agent_endpoint_off_the_machine_is_refused():
    persona = load_personas(PERSONAS)[0]
    persona.agent_endpoint = "https://remote.example.com/agent"
    window = Window([persona], StubLLM(), PrintTTS())
    with pytest.raises(LLMUnavailable):
        window.handle_text("How much have I spent on my card account this month?")


def test_an_agent_endpoint_on_a_clash_loopback_port_is_refused(monkeypatch):
    from window import http as window_http

    # 11434 is this machine's ollama and 8080 its DeepSeek. A persona endpoint aimed at one of
    # those loopback ports must be refused outright, not reached: with the HTTP library made
    # unimportable, a mere failed connection would come back as a "no answer" line, so a raised
    # LLMUnavailable here proves the port check rejects it before any request is attempted.
    monkeypatch.setattr(window_http, "requests", None)
    for url in ("http://127.0.0.1:11434/agent", "http://127.0.0.1:8080/agent"):
        persona = load_personas(PERSONAS)[0]
        persona.agent_endpoint = url
        window = Window([persona], StubLLM(), PrintTTS())
        with pytest.raises(LLMUnavailable):
            window.handle_text("How much have I spent on my card account this month?")


def test_a_non_loopback_tts_url_is_refused():
    from window.tts import VoiceVOXTTS
    for url in ("http://192.168.1.5:50021", "https://api.voicevox.example.com", "http://10.0.0.4:50021"):
        with pytest.raises(LLMUnavailable):
            VoiceVOXTTS(url=url)


def test_a_tts_url_on_a_clash_port_is_refused():
    from window.tts import VoiceVOXTTS
    for url in ("http://127.0.0.1:8080", "http://127.0.0.1:11434"):
        with pytest.raises(LLMUnavailable):
            VoiceVOXTTS(url=url)


def test_run_window_refuses_an_external_voicevox_url(monkeypatch, capsys):
    import run_window
    code = run_window.main(["--once", "How much have I spent on my card account this month?",
                            "--stub-llm", "--personas", str(PERSONAS),
                            "--tts", "voicevox", "--tts-url", "http://192.168.1.5:50021"])
    assert code == 1
    assert "the local voice engine endpoint is unusable" in capsys.readouterr().out


def test_stub_llm_mentions_being_a_machine():
    answer = StubLLM().chat([{"role": "system", "content": "brief"}, {"role": "user", "content": "cancel my card"}])
    assert "machine" in answer


def test_importing_the_package_pulls_in_every_part_of_the_desk():
    import importlib

    import window

    assert [name for name in window.__all__ if not hasattr(window, name)] == []
    for part in ("persona", "router", "guard", "llm", "asr", "tts", "window", "faces", "http"):
        importlib.import_module(f"window.{part}")
