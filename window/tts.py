"""Voice out. Only a local speech engine is contacted and the audio is played
from memory, never saved to disk."""

from __future__ import annotations

import os
from typing import Any

from .http import MissingDependency, require_requests
from .llm import assert_loopback
from .persona import Persona

DEFAULT_TTS_URL = "http://127.0.0.1:50021"


class ExternalSpeechForbidden(RuntimeError):
    pass


class PlaybackUnavailable(RuntimeError):
    """The engine produced audio, but no audio could actually be played on this machine."""


def _load_playback_modules():
    import numpy as np
    import sounddevice as sd

    return np, sd


class PrintTTS:
    """Writes the line the character would say; used when no engine is set up."""

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    def speak(self, persona: Persona, text: str) -> str:
        line = f"[{persona.name}] {text}"
        self.spoken.append((persona.id, text))
        print(line)
        return line

    def speak_to_outsider(self, persona: Persona, text: str) -> str:
        raise ExternalSpeechForbidden("the character never speaks to anyone outside the owner's machine")


class VoiceVOXTTS:
    def __init__(self, url: str | None = None, timeout: float = 20.0) -> None:
        self.url = (url or os.environ.get("AITUBER_TTS_URL") or DEFAULT_TTS_URL).rstrip("/")
        self.timeout = timeout
        assert_loopback(self.url)
        self.spoken: list[tuple[str, str]] = []

    def _requests(self):
        try:
            return require_requests()
        except MissingDependency as exc:
            raise RuntimeError(str(exc)) from exc

    def speak(self, persona: Persona, text: str) -> str:
        voice: dict[str, Any] = persona.voice or {}
        engine = str(voice.get("engine", "voicevox"))
        if engine != "voicevox":
            raise ExternalSpeechForbidden(f"voice engine {engine} is not a local one")
        requests = self._requests()
        query = {
            "speaker": int(voice.get("speaker_id", 1)),
            "speed": float(voice.get("speed", 1.0)),
            "pitch": float(voice.get("pitch", 0.0)),
            "volume": float(voice.get("volume", 1.0)),
        }
        try:
            response = requests.post(f"{self.url}/synthesis", params=query, data=text.encode("utf-8"),
                                     headers={"Content-Type": "application/octet-stream"}, timeout=self.timeout)
            response.raise_for_status()
            audio = response.content
        except requests.RequestException as exc:
            raise RuntimeError(f"local voice engine at {self.url} is not reachable: {exc}") from exc
        self._play(audio)
        self.spoken.append((persona.id, text))
        return f"[{persona.name}] {text}"

    def speak_to_outsider(self, persona: Persona, text: str) -> str:
        raise ExternalSpeechForbidden("the character never speaks to anyone outside the owner's machine")

    def _play(self, audio: bytes) -> None:
        if not audio:
            raise PlaybackUnavailable("the voice engine returned no audio")
        if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise PlaybackUnavailable("the voice engine returned audio that is not playable WAV")
        try:
            import io
            import wave

            np, sd = _load_playback_modules()
        except ImportError as exc:
            raise PlaybackUnavailable(
                f"audio was synthesized but nothing was played: {exc} is missing "
                "(pip install -r requirements-mic.txt, or run with --tts print)") from exc
        try:
            with wave.open(io.BytesIO(audio), "rb") as handle:
                frames = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
                sd.play(frames, samplerate=handle.getframerate())
                sd.wait()
        except (wave.Error, EOFError, ValueError, OSError) as exc:
            raise PlaybackUnavailable(f"local audio playback failed: {exc}") from exc
