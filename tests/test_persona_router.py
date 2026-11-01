from pathlib import Path

from window.persona import load_personas
from window.router import route

PERSONAS = Path(__file__).resolve().parent.parent / "personas"


def test_persona_file_carries_name_look_and_voice():
    persona = load_personas(PERSONAS)[0]
    assert persona.id == "account-keeper"
    assert persona.name and persona.title
    assert persona.look and persona.avatar
    assert persona.voice["engine"] == "voicevox"
    assert persona.speech_style and persona.agent_brief
    assert "machine" in persona.speech_style.lower()


def test_persona_prompt_names_the_character_and_its_style():
    persona = load_personas(PERSONAS)[0]
    prompt = persona.system_prompt()
    assert persona.name in prompt
    assert persona.title in prompt


def test_route_sends_account_questions_to_the_account_keeper():
    persona = load_personas(PERSONAS)[0]
    match = route([persona], "How much have I spent on my card account this month?")
    assert match is not None
    assert match.persona.id == "account-keeper"
    assert match.score > 0


def test_route_japanese_card_question():
    persona = load_personas(PERSONAS)[0]
    match = route([persona], "カードの請求を確認したい")
    assert match is not None and match.persona.id == "account-keeper"


def test_route_leaves_unrelated_requests_unmatched():
    persona = load_personas(PERSONAS)[0]
    assert route([persona], "What should I wear to a wedding tomorrow?") is None
