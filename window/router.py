"""Pick which agent's persona answers an utterance."""

from __future__ import annotations

from dataclasses import dataclass

from .persona import Persona, keyword_matches


@dataclass
class Match:
    persona: Persona
    topic: str
    score: int

    @property
    def persona_id(self) -> str:
        return self.persona.id


def score_persona(persona: Persona, text: str) -> tuple[int, str]:
    lowered = text.lower()
    best_topic = ""
    best = 0
    for handle in persona.handles:
        hits = sum(1 for keyword in handle.keywords if keyword_matches(keyword, lowered))
        if hits > best:
            best = hits
            best_topic = handle.topic
    return best, best_topic


def route(personas: list[Persona], text: str) -> Match | None:
    """Best keyword match wins; the persona marked default is the fallback."""
    ranked = sorted(((score_persona(p, text), p) for p in personas), key=lambda item: (-item[0][0], item[1].id))
    if not ranked:
        return None
    (score, topic), persona = ranked[0]
    if score > 0:
        return Match(persona, topic, score)
    fallback = next((p for p in personas if p.default), None)
    if fallback is None:
        return None
    return Match(fallback, "general", 0)
