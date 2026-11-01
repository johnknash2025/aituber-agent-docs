"""The same face can be reused where the dashboard lists the agents at work.

Run ``python3 -m window personas`` to print the catalog as JSON on stdout; this
module's ``main`` does the printing and nothing here is written to disk, the
dashboard decides where to keep it. (``python3 -m window.faces personas`` also
works, but the recommended path avoids Python's "already in sys.modules" warning.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .persona import Persona, load_personas


def face_catalog(personas: list[Persona]) -> dict[str, dict[str, Any]]:
    return {
        persona.id: {
            "name": persona.name,
            "title": persona.title,
            "look": persona.look,
            "avatar": persona.avatar,
            "voice": persona.voice,
            "topics": [handle.topic for handle in persona.handles],
        }
        for persona in personas
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    directory = Path(argv[0] if argv else "personas")
    print(json.dumps(face_catalog(load_personas(directory)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
