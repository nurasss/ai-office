from tools.external.telegram import sanitize_telegram_text


def test_sanitize_telegram_text_removes_markdown_formatting():
    text = "**Заголовок**\n- _важно_: `OK`\n[источник](https://example.com)"

    assert sanitize_telegram_text(text) == (
        "Заголовок\n"
        "важно: OK\n"
        "источник (https://example.com)"
    )
