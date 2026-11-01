from pathlib import Path

from window.faces import face_catalog
from window.persona import load_personas

PERSONAS = Path(__file__).resolve().parent.parent / "personas"


def test_dashboard_can_reuse_the_same_face():
    catalog = face_catalog(load_personas(PERSONAS))
    assert catalog["account-keeper"]["name"]
    assert catalog["account-keeper"]["look"]
    assert catalog["account-keeper"]["avatar"]
    assert "accounts and cards" in catalog["account-keeper"]["topics"]
