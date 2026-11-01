"""Package entry point: ``python3 -m window personas`` prints the face catalog as JSON.

This exists so the documented command in the README runs cleanly. Running
``python3 -m window.faces ...`` still works, but Python warns that ``window.faces``
is already in ``sys.modules`` because the package imports it during startup; the
``-m window`` path avoids that warning and points at the same code.
"""

from __future__ import annotations

import sys

from .faces import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
