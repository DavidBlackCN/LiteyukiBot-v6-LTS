from pathlib import Path


def test_empty_sections_are_forced_hidden_and_footer_is_readable() -> None:
    css = Path("src/resources/liteyuki_60s/templates/css/sixty_card.css").read_text(
        encoding="utf-8"
    )
    assert "#quote-box[hidden], #facts[hidden], #progress-box[hidden], #items[hidden]" in css
    assert "display: none !important" in css
    assert ".card-date:empty, .headline:empty" in css
    assert ".card-background-page.has-remote-background .card-footer" in css
    assert "background: rgba(255, 255, 255, 0.92)" in css
