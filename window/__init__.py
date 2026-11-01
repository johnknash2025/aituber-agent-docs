"""Persona front desk for AITuber agents.

A character (persona) is the door to an agent: speech in, transcription in
memory only, handoff to the responsible agent, spoken answer out. Local model
only, no audio persisted, no action without the owner confirming.

Run ``python3 -m window personas`` to print the face catalog; ``window/__main__.py``
dispatches to ``window.faces.main``. The heavy optional extras (numpy, sounddevice,
vosk) stay out of this module so importing ``window`` never needs them.
"""

from __future__ import annotations

from typing import Any

from .persona import Persona, load_personas
from .router import Match, route
from .guard import Guard, Risk, PERSONA_GUARDRAILS
from .llm import LocalLLM, StubLLM, LLMUnavailable
from .asr import MockTranscriber, TextTranscriber, VoskTranscriber
from .tts import PrintTTS, VoiceVOXTTS
from .window import Window, TurnResult
from .http import MissingDependency


def __getattr__(name: str) -> Any:
    # ``face_catalog`` is loaded on first use so ``python3 -m window.faces`` does not
    # hit Python's "already imported" warning when the package pulls faces in eagerly.
    if name == "face_catalog":
        from .faces import face_catalog as _face_catalog
        return _face_catalog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Persona",
    "load_personas",
    "Match",
    "route",
    "Guard",
    "Risk",
    "PERSONA_GUARDRAILS",
    "LocalLLM",
    "StubLLM",
    "LLMUnavailable",
    "MissingDependency",
    "MockTranscriber",
    "TextTranscriber",
    "VoskTranscriber",
    "PrintTTS",
    "VoiceVOXTTS",
    "Window",
    "TurnResult",
    "face_catalog",
]

__version__ = "0.1.0"
