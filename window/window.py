"""The front desk itself: speech in, handoff to the responsible agent, the
answer comes back through the character's voice."""

from __future__ import annotations

from dataclasses import dataclass, field

from .guard import Guard, PERSONA_GUARDRAILS, Risk, redact_secrets
from .http import http_error_types, require_requests
from .llm import LLMUnavailable, assert_loopback, ensure_machine_disclosure
from .persona import Persona
from .router import Match, route

MESSAGES = {
    "no_text": {
        "en": "I did not catch that. Say it again.",
        "ja": "聞こえませんでした。もう一度言ってください。",
    },
    "no_agent": {
        "en": "I could not reach the local model, so I have no answer for you. Nothing was sent anywhere else.",
        "ja": "ローカルの頭に届かず、答えが出せません。他に送ることはしていません。",
    },
    "unknown_topic": {
        "en": "I am only the front desk for one agent, and this does not look like its job. I will not guess an answer.",
        "ja": "私は一人分の窓口だけです。これはその担当の仕事ではないようです。勝手に答えは出しません。",
    },
    "third_party": {
        "en": ("I do not take instructions that came from someone else, and I do not pass your words on. "
               "If you want to act on it, check with the company yourself."),
        "ja": ("私は外から来た指示には従いません。あなたの言葉を代わりに伝えることもしません。"
               "進めるなら、自分で会社に確かめてください。"),
    },
    "confirm_ask": {
        "en": ("This touches money or something that cannot be undone. I will not do it. "
               "Say yes if you want the steps laid out, say no to drop it."),
        "ja": ("お金が動くか、元に戻せない操作です。私は実行しません。手順を聞くなら「はい」、"
               "やめるなら「いいえ」と言ってください。"),
    },
    "confirmed_done": {
        "en": ("You said yes. I have no hands on your accounts, so nothing happened here. "
               "You do the steps yourself, and I can write down what you decided."),
        "ja": ("「はい」と聞きました。私は口座に直接触らないので、ここでは何も起きていません。"
               "操作はご本人がしてください。決めたことは記録できます。"),
    },
    "steps_prefix": {"en": "The steps, as I described them:", "ja": "私が説明した手順:"},
    "denied": {
        "en": "Dropped. Nothing was changed and nothing will be.",
        "ja": "やめました。何も変更していませんし、変更しません。",
    },
    "awaiting": {
        "en": "I still need a clear yes or no before I lay out any steps.",
        "ja": "手順を説明する前に、はっきり「はい」か「いいえ」を教えてください。",
    },
}


def detect_language(text: str) -> str:
    return "ja" if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in text) else "en"


@dataclass
class TurnResult:
    transcript: str
    persona_id: str | None
    topic: str | None
    agent_answer: str
    reply: str
    spoken: str
    language: str = "en"
    risks: list[Risk] = field(default_factory=list)
    needs_confirmation: bool = False
    blocked: bool = False
    handed_off: bool = False


class Window:
    def __init__(self, personas: list[Persona], llm, tts, guard: Guard | None = None) -> None:
        if not personas:
            raise ValueError("at least one persona is required")
        self.personas = personas
        self.llm = llm
        self.tts = tts
        self.guard = guard or Guard()
        self._pending_persona_id: str | None = None
        self._pending_language = "en"

    def handle_audio(self, audio: bytes, transcriber) -> TurnResult:
        transcript = transcriber.transcribe(audio)
        try:
            result = self.handle_text(transcript)
            result.transcript = transcript
            return result
        finally:
            self.forget_transcript()

    def handle_text(self, transcript: str) -> TurnResult:
        text = redact_secrets((transcript or "").strip())
        language = detect_language(text)
        if not text:
            return self._speak(None, None, self._msg("no_text", language), language=language)

        if self.guard.pending is not None:
            new_risks = self.guard.assess(text)
            new_dangerous = any(r.needs_confirmation or r.blocked for r in new_risks)
            decision = self.guard.resolve(text)
            if not new_dangerous and decision == "confirmed":
                return self._confirm_handoff()
            if not new_dangerous and decision == "denied":
                persona = self._pending_persona()
                lang = self._pending_language
                self._clear_pending()
                return self._speak(persona, None, self._msg("denied", lang), language=lang)
            if not new_dangerous:
                return self._speak(self._pending_persona(), None,
                                   self._msg("awaiting", self._pending_language), language=self._pending_language)
            self._clear_pending()

        match = route(self.personas, text)
        risks = self.guard.assess(text)

        blocked = next((r for r in risks if r.blocked), None)
        if blocked is not None:
            return self._speak(match.persona if match else None, match.topic if match else None,
                               self._msg("third_party", language), risks=risks, blocked=True, language=language)

        if match is None:
            dangerous = next((r for r in risks if r.needs_confirmation), None)
            if dangerous is None:
                return self._speak(None, None, self._msg("unknown_topic", language), language=language)
            self._pending_persona_id = None
            self._pending_language = language
            self.guard.hold(dangerous, "")
            reply = f"{self._msg('unknown_topic', language)} {self._msg('confirm_ask', language)}"
            return self._speak(None, None, reply, risks=risks, needs_confirmation=True, language=language)

        agent_answer = self._ask_agent(match.persona, text)
        if any(r.blocked and r.category == "third_party_instruction" for r in self.guard.assess(agent_answer)):
            return self._speak(match.persona, match.topic, self._msg("third_party", language), agent_answer="",
                               risks=risks, blocked=True, language=language)
        reply = self._phrase(match.persona, agent_answer, language)
        needs_confirmation = any(r.needs_confirmation for r in risks)
        if needs_confirmation:
            reply = f"{reply} {self._msg('confirm_ask', language)}"
            self._pending_persona_id = match.persona.id
            self._pending_language = language
            self.guard.hold(next(r for r in risks if r.needs_confirmation), agent_answer)
        return self._speak(match.persona, match.topic, reply, agent_answer=agent_answer, risks=risks,
                           needs_confirmation=needs_confirmation, language=language)

    def confirm(self, text: str) -> TurnResult:
        decision = self.guard.resolve(text)
        if decision == "confirmed":
            return self._confirm_handoff()
        if decision == "denied":
            persona = self._pending_persona()
            lang = self._pending_language
            self._clear_pending()
            return self._speak(persona, None, self._msg("denied", lang), language=lang)
        return self._speak(self._pending_persona(), None, self._msg("awaiting", self._pending_language),
                           language=self._pending_language)

    def forget_transcript(self) -> None:
        """The transcript lives only inside this call; nothing about it reaches disk."""
        return None

    def _clear_pending(self) -> None:
        self.guard.clear()
        self._pending_persona_id = None
        self._pending_language = "en"

    def _confirm_handoff(self) -> TurnResult:
        plan = self.guard.pending_plan
        persona = self._pending_persona()
        lang = self._pending_language
        self._clear_pending()
        lines = [self._msg("confirmed_done", lang)]
        if plan:
            lines.append(f"{self._msg('steps_prefix', lang)} {plan}")
        return self._speak(persona, "confirmed plan", " ".join(lines), agent_answer=plan, handed_off=True,
                           language=lang)

    def _pending_persona(self) -> Persona | None:
        return next((p for p in self.personas if p.id == self._pending_persona_id), None)

    def _ask_agent(self, persona: Persona, text: str) -> str:
        if persona.agent_endpoint:
            assert_loopback(persona.agent_endpoint)
            try:
                requests = require_requests()
                response = requests.post(persona.agent_endpoint, json={"text": text, "persona": persona.id},
                                         timeout=60)
                response.raise_for_status()
                body = response.json()
            except http_error_types():
                return self._msg("no_agent", detect_language(text))
            if not isinstance(body, dict):
                return self._msg("no_agent", detect_language(text))
            return redact_secrets(str(body.get("reply", "")).strip()) or self._msg("no_agent", "en")
        messages = [
            {"role": "system", "content": f"{persona.agent_brief} {PERSONA_GUARDRAILS} "
                                          "Answer in at most five short sentences, in the language of the owner."},
            {"role": "user", "content": text},
        ]
        try:
            return self.llm.chat(messages, max_tokens=800)
        except LLMUnavailable:
            return self._msg("no_agent", detect_language(text))

    def _phrase(self, persona: Persona, agent_answer: str, language: str) -> str:
        messages = [
            {"role": "system", "content": f"{persona.system_prompt()} {PERSONA_GUARDRAILS} "
                                          "Restate the agent's answer in your own style. Keep every fact, every "
                                          "warning and every request for confirmation. Add no new instruction to act. "
                                          "Use the language of the answer."},
            {"role": "user", "content": agent_answer},
        ]
        try:
            return ensure_machine_disclosure(self.llm.chat(messages, max_tokens=800))
        except LLMUnavailable:
            return ensure_machine_disclosure(agent_answer)

    def _msg(self, key: str, language: str) -> str:
        return MESSAGES[key][language if language in MESSAGES[key] else "en"]

    def _speak(self, persona: Persona | None, topic: str | None, reply: str, agent_answer: str = "",
               risks: list[Risk] | None = None, needs_confirmation: bool = False, blocked: bool = False,
               handed_off: bool = False, language: str = "en") -> TurnResult:
        speaker = persona or self._desk_persona()
        spoken = self.tts.speak(speaker, reply)
        return TurnResult(transcript="", persona_id=persona.id if persona else None, topic=topic,
                          agent_answer=agent_answer, reply=reply, spoken=spoken, language=language,
                          risks=risks or [], needs_confirmation=needs_confirmation, blocked=blocked,
                          handed_off=handed_off)

    def _desk_persona(self) -> Persona:
        return self.personas[0]


def summarise(match: Match | None) -> str:
    return f"{match.persona.id}:{match.topic}" if match else "no match"
