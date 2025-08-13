from annex4parser.regulation_monitor import _sanitize_content, parse_rules


def test_sanitize_content_preserves_marker_with_text():
    raw = "(a)\nSome point"
    assert _sanitize_content(raw).startswith("(a)\nSome point")


def test_sanitize_content_drops_hanging_marker():
    raw = "(a)\n\n"
    assert _sanitize_content(raw) == ""


def test_sanitize_content_preserves_marker_with_blank_line():
    raw = "(a)\n\nNext"
    assert _sanitize_content(raw).startswith("(a)")


def test_parse_rules_with_separate_marker_line():
    text = "Article 1\n1.\n(a)\nSubpoint text\n"
    rules = parse_rules(text)
    sub = next(r for r in rules if r["section_code"] == "Article1.1.a")
    assert "Subpoint text" in sub["content"]
