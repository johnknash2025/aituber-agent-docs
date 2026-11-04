"""HTTP seam. The requests package is a declared dependency (requirements.txt), but it is
imported lazily so the offline demo and the test suite still run where it is not installed;
using the network without it is refused with a usable message instead of an ImportError.

The optional microphone and audio-playback extras (numpy, sounddevice, vosk) live in
requirements-mic.txt; they are not imported here and are loaded by window.asr / window.tts
only when the code path that needs them is actually entered."""

from __future__ import annotations

from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - depends on the environment
    requests = None  # type: ignore[assignment]

INSTALL_HINT = (
    "install the requests package: pip install -r requirements.txt "
    "(pip install -r requirements-mic.txt if you also want --mic or real VOICEVOX playback)"
)


class MissingDependency(RuntimeError):
    pass


def require_requests() -> Any:
    if requests is None:
        raise MissingDependency(f"this needs a local HTTP call: {INSTALL_HINT}")
    return requests


def http_error_types() -> tuple[type[BaseException], ...]:
    """Exception classes that mean 'the call failed', safe to use even when requests is absent."""
    if requests is None:
        return (MissingDependency,)
    return (requests.RequestException, ValueError, TypeError)
