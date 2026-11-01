"""Persona files: name, look, voice and speech style per agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def keyword_matches(keyword: str, lowered_text: str) -> bool:
    """Latin keywords match as whole words (so 'id' never matches 'provide'); CJK keywords use substring."""
    kw = keyword.lower()
    if kw.isascii() and kw.isalnum():
        return re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", lowered_text) is not None
    return kw in lowered_text


@dataclass
class Handle:
    topic: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class Persona:
    id: str
    name: str
    title: str
    look: str
    avatar: str
    voice: dict[str, Any]
    speech_style: str
    agent_brief: str
    handles: list[Handle]
    default: bool = False
    agent_endpoint: str = ""
    source: Path | None = None

    def matches(self, word: str) -> bool:
        lowered = word.lower()
        for handle in self.handles:
            for keyword in handle.keywords:
                if keyword_matches(keyword, lowered):
                    return True
        return False

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, the {self.title} character of the {self.id} agent. "
            f"Appearance for stage directions only: {self.look}. "
            f"Speech style: {self.speech_style}"
        )


def load_persona(path: Path) -> Persona:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    handles = [Handle(topic=h.get("topic", ""), keywords=list(h.get("keywords", []))) for h in raw.get("handles", [])]
    return Persona(
        id=raw["id"],
        name=raw["name"],
        title=raw.get("title", raw["id"]),
        look=raw.get("look", ""),
        avatar=raw.get("avatar", ""),
        voice=dict(raw.get("voice", {})),
        speech_style=raw.get("speech_style", ""),
        agent_brief=raw.get("agent_brief", ""),
        handles=handles,
        default=bool(raw.get("default", False)),
        agent_endpoint=raw.get("agent_endpoint", ""),
        source=Path(path),
    )


def load_personas(directory: Path) -> list[Persona]:
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"persona directory not found: {directory}")
    personas = [load_persona(p) for p in sorted(directory.glob("*.json"))]
    if not personas:
        raise ValueError(f"no persona files in {directory}")
    return personas
