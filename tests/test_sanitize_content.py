from annex4parser.regulation_monitor import _sanitize_content, parse_rules
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2


def test_sanitize_content_preserves_marker_with_text():
    raw = "(a)\nSome point"
    assert _sanitize_content(raw).startswith("(a) Some point")


def test_sanitize_content_drops_hanging_marker():
    raw = "(a)\n\n"
    assert _sanitize_content(raw) == ""


def test_sanitize_content_preserves_marker_with_blank_line():
    raw = "(a)\n\nNext"
    assert _sanitize_content(raw).startswith("(a)")


def test_parse_rules_with_separate_marker_line():
    text = "Article 1\n1.\n(a)\nThe provider shall ensure\n"
    rules = parse_rules(text)
    sub = next(r for r in rules if r["section_code"] == "Article1.1.a")
    assert "provider shall ensure" in sub["content"]


def test_sanitize_content_removes_annexe_and_lang_markers():
    raw = "ANNEXE IV\nEN\nFR\nSome text"
    assert _sanitize_content(raw) == "Some text"


def test_sanitize_content_unwraps_soft_linebreaks():
    raw = "including with other AI\nsystems, that are not"
    assert _sanitize_content(raw) == "including with other AI systems, that are not"


def test_sanitize_content_unwraps_hyphen_breaks():
    raw = "inter-\noperability"
    assert _sanitize_content(raw) == "interoperability"


def test_sanitize_content_removes_eli_footer():
    raw = "Some text\nELI: http://example.com/eli/123\nNext"
    assert _sanitize_content(raw) == "Some text\n\nNext"


def test_sanitize_text_unwraps_soft_linebreaks():
    monitor = RegulationMonitorV2.__new__(RegulationMonitorV2)
    raw = "including with other AI\nsystems, that are not"
    assert monitor._sanitize_text(raw) == "including with other AI systems, that are not"


def test_sanitize_text_removes_eli_footer():
    monitor = RegulationMonitorV2.__new__(RegulationMonitorV2)
    raw = "Some text\nELI: http://example.com/eli/123\nNext"
    assert monitor._sanitize_text(raw) == "Some text\n\nNext"


def test_sanitizers_drop_inline_eli_and_bare_url():
    raw = "Some text (ELI: http://data.europa.eu/eli/reg/2024/1689/oj).\nNext"
    assert _sanitize_content(raw) == "Some text.\n\nNext"
    mon = RegulationMonitorV2.__new__(RegulationMonitorV2)
    assert mon._sanitize_text(raw) == "Some text.\n\nNext"


def test_sanitizers_drop_oj_footer_and_page_counter():
    raw = "Clause...\n45/144\nEN OJ L, 12.7.2024\n"
    assert _sanitize_content(raw) == "Clause..."
    mon = RegulationMonitorV2.__new__(RegulationMonitorV2)
    assert mon._sanitize_text(raw) == "Clause..."
