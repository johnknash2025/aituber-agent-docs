"""Speech in. Audio stays in memory: no recording file is ever written and a
transcript is kept only while it is being used."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_SAMPLE_RATE = 16000
MAX_CAPTURE_SECONDS = 15.0


def record_from_mic(seconds: float = 4.0, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """Capture one short utterance into memory. Requires numpy and sounddevice."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "mic capture needs numpy and sounddevice "
            "(pip install -r requirements-mic.txt); run with --text instead") from exc
    capped = max(0.01, min(seconds, MAX_CAPTURE_SECONDS))
    try:
        frames = sd.rec(int(capped * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
        sd.wait()
    except Exception as exc:
        raise RuntimeError(f"microphone capture failed on this machine: {exc}; run with --text instead") from exc
    audio = bytes(np.asarray(frames).tobytes())
    del frames
    return audio


class MockTranscriber:
    """Hands back a scripted line per call; used by tests and the offline demo."""

    def __init__(self, script: Sequence[str]) -> None:
        self._script = list(script)
        self._index = 0
        self.received_bytes = 0

    def transcribe(self, audio: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        self.received_bytes += len(audio)
        if self._index >= len(self._script):
            return ""
        line = self._script[self._index]
        self._index += 1
        return line


class VoskTranscriber:
    """Local offline recogniser; audio bytes are fed straight into the recognizer."""

    def __init__(self, model_path: str | None = None, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        path = model_path or os.environ.get("AITUBER_VOSK_MODEL", "")
        if not path:
            raise RuntimeError("set AITUBER_VOSK_MODEL to a local vosk model directory, or pass --vosk-model")
        if not Path(path).is_dir():
            raise RuntimeError(f"vosk model directory not found: {path}")
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise RuntimeError("vosk is not installed (pip install -r requirements-mic.txt); run with --text instead") from exc
        try:
            model = Model(path)
        except (OSError, RuntimeError) as exc:
            raise RuntimeError(f"could not load the vosk model at {path}: {exc}") from exc
        if model is None:
            raise RuntimeError(f"could not load the vosk model at {path}: the directory has no usable model")
        self._model = model
        self._sample_rate = sample_rate
        self._recognizer_cls = KaldiRecognizer

    def transcribe(self, audio: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        """Return the recognised text, or "" when the recogniser hands back nothing usable.

        A malformed FinalResult (not JSON, or JSON that is not an object) is treated as an empty
        transcript instead of raising, so one bad recogniser output cannot crash the door."""
        import json

        recognizer = self._recognizer_cls(self._model, sample_rate or self._sample_rate)
        recognizer.AcceptWaveform(audio)
        try:
            parsed = json.loads(recognizer.FinalResult())
        except ValueError:
            return ""
        if not isinstance(parsed, dict):
            return ""
        return str(parsed.get("text", "")).strip()


class TextTranscriber:
    """Keyboard stand-in for a microphone, so the door works without audio hardware."""

    def __init__(self, prompt: str = "you> ", script: Iterable[str] | None = None) -> None:
        self._prompt = prompt
        self._script = list(script) if script is not None else None
        self._index = 0

    def transcribe(self, audio: bytes | None = None, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        if self._script is not None:
            if self._index >= len(self._script):
                return ""
            line = self._script[self._index]
            self._index += 1
            return line
        return input(self._prompt).strip()
