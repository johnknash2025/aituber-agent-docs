#!/usr/bin/env python3
"""Talk to an agent through its character.

  python3 run_window.py --demo            scripted offline walk-through
  python3 run_window.py --text            type instead of speaking
  python3 run_window.py --mic             speak (run: pip install -r requirements-mic.txt)

The --demo, --text and --tts print paths need only the core requirements; the
--mic path and real VOICEVOX playback pull numpy, sounddevice and vosk lazily.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from window.asr import MockTranscriber, TextTranscriber, VoskTranscriber, record_from_mic
from window.llm import LLMUnavailable, LocalLLM, StubLLM
from window.persona import load_personas
from window.tts import PrintTTS, VoiceVOXTTS
from window.window import Window

DEMO_SCRIPT = [
    "How much have I spent on my card account this month?",
    "Cancel this card for me.",
    "yes",
]

SILENT_TURNS_BEFORE_EXIT = 3


class FallbackTTS:
    """Speak through the primary engine; if it is unreachable, fall back to printing the line.

    ``spoken`` records every line that this desk actually delivered, whichever engine said it."""

    def __init__(self, primary, fallback: PrintTTS) -> None:
        self.primary = primary
        self.fallback = fallback
        self.spoken: list[tuple[str, str]] = []

    def speak(self, persona, text: str) -> str:
        try:
            line = self.primary.speak(persona, text)
        except Exception as exc:  # any primary-engine failure falls back to printed text
            print(f"voice engine unavailable ({exc}); speaking as text")
            line = self.fallback.speak(persona, text)
        self.spoken.append((persona.id, text))
        return line

    def speak_to_outsider(self, persona, text: str) -> str:
        return self.primary.speak_to_outsider(persona, text)


def build_llm(args):
    if args.stub_llm or args.demo:
        # The demo never talks to a model, so a broken or refused AITUBER_LLM_URL must not stop it.
        return StubLLM()
    return LocalLLM(url=args.llm_url)


def build_tts(args):
    if args.tts == "voicevox":
        return FallbackTTS(VoiceVOXTTS(url=args.tts_url), PrintTTS())
    return PrintTTS()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="persona front desk for AITuber agents")
    parser.add_argument("--personas", default="personas", help="directory of persona json files")
    parser.add_argument("--llm-url", default=None, help="local OpenAI-compatible endpoint, loopback only")
    parser.add_argument("--stub-llm", action="store_true", help="offline stand-in for the local model (demo and tests)")
    parser.add_argument("--tts", choices=["print", "voicevox"], default="print")
    parser.add_argument("--tts-url", default=None, help="local VOICEVOX URL, loopback only")
    parser.add_argument("--text", action="store_true", help="type instead of speaking (the default)")
    parser.add_argument("--mic", action="store_true", help="capture one utterance per turn from the microphone")
    parser.add_argument("--seconds", type=float, default=4.0, help="microphone capture length")
    parser.add_argument("--vosk-model", default=None, help="local vosk model directory")
    parser.add_argument("--demo", action="store_true", help="run the scripted walk-through with a stub model")
    parser.add_argument("--once", default=None, help="answer a single sentence and exit")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    personas = load_personas(Path(args.personas))
    print(f"personas: {', '.join(f'{p.id} as {p.name}' for p in personas)}")

    try:
        llm = build_llm(args)
    except LLMUnavailable as exc:
        print(f"the local model endpoint is unusable: {exc}")
        return 1

    try:
        tts = build_tts(args)
    except LLMUnavailable as exc:
        print(f"the local voice engine endpoint is unusable: {exc}")
        return 1

    window = Window(personas, llm, tts)

    if args.once:
        result = window.handle_text(args.once)
        if result.needs_confirmation and window.guard.pending is not None:
            try:
                answer = input("confirm? (yes/no) > ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            window.confirm(answer)
        return 0

    if args.demo:
        transcript_source = MockTranscriber(DEMO_SCRIPT)
        for _ in DEMO_SCRIPT:
            result = window.handle_audio(b"\x00\x00\x01\x01" * 8, transcript_source)
            print(f"    -> agent={result.persona_id or '-'} topic={result.topic or '-'} "
                  f"confirm_needed={result.needs_confirmation}")
        return 0

    if args.mic:
        try:
            transcriber = VoskTranscriber(model_path=args.vosk_model)
        except RuntimeError as exc:
            print(exc)
            return 1
        silent_turns = 0
        while silent_turns < SILENT_TURNS_BEFORE_EXIT:
            try:
                audio = record_from_mic(seconds=args.seconds)
            except RuntimeError as exc:
                print(exc)
                return 1
            result = window.handle_audio(audio, transcriber)
            if not result.transcript.strip():
                silent_turns += 1
                continue
            silent_turns = 0
            if result.needs_confirmation and window.guard.pending is not None:
                try:
                    confirm_audio = record_from_mic(seconds=args.seconds)
                except RuntimeError as exc:
                    print(exc)
                    return 1
                window.confirm(transcriber.transcribe(confirm_audio))
        if silent_turns:
            print("no speech heard for a while; ending the session")
        return 0

    transcriber = TextTranscriber()
    while True:
        try:
            text = transcriber.transcribe()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            return 0
        window.handle_text(text)


if __name__ == "__main__":
    raise SystemExit(main())
