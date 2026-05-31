from security.pii import redact_pii


def test_redacts_email_phone_iin_token():
    result = redact_pii("Email test@example.com phone +77011234567 IIN 123456789012 token xoxb-1234567890-fake")

    assert "[EMAIL_REDACTED]" in result.redacted_text
    assert "[PHONE_REDACTED]" in result.redacted_text
    assert "[IIN_REDACTED]" in result.redacted_text
    assert "[TOKEN_REDACTED]" in result.redacted_text
    assert {finding.kind for finding in result.findings} >= {"EMAIL", "PHONE", "IIN", "TOKEN"}
