from triage.privacy import redact


def test_emails_phones_and_bank_numbers_are_masked():
    text = ("Hi, I'm anna.kowalska@example.com, call me at +48 601 234 567 or 601-234-567. "
            "Refund to PL61 1090 1014 0000 0712 1981 2874 please.")
    r = redact(text)
    assert "anna.kowalska" not in r.text and "601" not in r.text and "1090" not in r.text
    assert r.text.count("[EMAIL]") == 1
    assert r.text.count("[PHONE]") == 2
    assert r.text.count("[IBAN]") == 1
    assert r.counts == {"email": 1, "phone": 2, "iban": 1}


def test_order_numbers_are_kept_and_extracted():
    r = redact("Zamówienie TY-2048813 nie dotarło, a #3301977 też nie. Tel. 512345678")
    assert "TY-2048813" in r.text
    assert r.order_ids == ["TY-2048813", "TY-3301977"]
    assert "[PHONE]" in r.text


def test_text_without_personal_data_is_unchanged():
    text = "The shelf arrived scratched, order TY-1000001."
    r = redact(text)
    assert r.text == text and r.counts == {}
