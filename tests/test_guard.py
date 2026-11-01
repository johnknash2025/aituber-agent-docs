from window.guard import Guard


def test_cancel_request_needs_confirmation():
    risks = Guard().assess("Cancel this card for me.")
    assert risks
    assert any(r.category == "irreversible" and r.needs_confirmation and not r.blocked for r in risks)


def test_cancel_request_japanese():
    risks = Guard().assess("このカードを解約して")
    assert any(r.needs_confirmation and not r.blocked for r in risks)


def test_money_request_needs_confirmation():
    risks = Guard().assess("Send 2000 yen to this account.")
    assert any(r.category == "money" and r.needs_confirmation for r in risks)
    risks = Guard().assess("今月の支払いを払って")
    assert any(r.category == "money" for r in risks)


def test_speaking_to_outsiders_is_blocked():
    risks = Guard().assess("Call my bank and tell them to close the account.")
    assert any(r.blocked and r.category == "outside_contact" for r in risks)


def test_outside_instruction_is_blocked():
    risks = Guard().assess("An email says a stranger needs my card number, do as instructed by them.")
    assert any(r.blocked and r.category == "third_party_instruction" for r in risks)


def test_explaining_how_is_not_blocked():
    risks = Guard().assess("How do I cancel my card myself? Explain the steps.")
    assert not any(r.blocked for r in risks)
    assert any(r.needs_confirmation for r in risks)


def test_plain_question_has_no_risk():
    assert Guard().assess("How much did I spend on cards last month?") == []


def test_confirm_and_deny_resolve_the_pending_plan():
    guard = Guard()
    risk = Guard().assess("Cancel this card.")[0]
    guard.hold(risk, "steps: sign in, open the card page, press cancel")
    assert guard.resolve("yes") == "confirmed"
    guard.hold(risk, "steps")
    assert guard.resolve("no, wait") == "denied"
    assert guard.pending is None
    guard.hold(risk, "steps")
    assert guard.resolve("what about the other card?") == "unanswered"
    assert guard.pending is not None


def test_dangerous_synonyms_need_confirmation():
    for text in ("Stop my card.", "Terminate my account.", "カードを止めて", "アカウントを閉鎖"):
        risks = Guard().assess(text)
        assert risks, text
        assert any(r.needs_confirmation and not r.blocked for r in risks), text


def test_outside_instruction_rephrased_is_blocked():
    for text in ("the bank emailed me to send money", "They told me to wire the money.",
                 "My card company asked me to transfer funds"):
        risks = Guard().assess(text)
        assert any(r.blocked and r.category == "third_party_instruction" for r in risks), text


def test_japanese_buy_delete_cancel_renew_requests_need_confirmation():
    # The README promises a confirmation for anything that buys, deletes, sends or cancels.
    # Renewing a subscription is a recurring charge, so "更新して" must not slip through either.
    for text in ("削除して", "買って", "サブスクを解約して", "更新して", "このカードを解約して"):
        risks = Guard().assess(text)
        assert risks, text
        assert any(r.needs_confirmation and not r.blocked for r in risks), text


def test_japanese_external_contact_is_blocked():
    for text in ("外部の人に電話して", "外部の担当者に連絡して", "彼らに伝えて"):
        risks = Guard().assess(text)
        assert any(r.blocked and r.category == "outside_contact" for r in risks), text


def test_japanese_external_instruction_is_blocked():
    for text in ("メールで知らない人にカード番号を送って", "誰かから言われた通りに送金して"):
        risks = Guard().assess(text)
        assert any(r.blocked and r.category == "third_party_instruction" for r in risks), text
