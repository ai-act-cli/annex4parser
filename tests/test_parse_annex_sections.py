import importlib.util
import types
import sys
from pathlib import Path

pkg_path = Path(__file__).resolve().parents[1] / "annex4parser"
pkg = types.ModuleType("annex4parser")
pkg.__path__ = [str(pkg_path)]
sys.modules.setdefault("annex4parser", pkg)

spec = importlib.util.spec_from_file_location(
    "annex4parser.regulation_monitor", pkg_path / "regulation_monitor.py"
)
regulation_monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regulation_monitor)
parse_rules = regulation_monitor.parse_rules


def test_parse_annex_viii_with_sections_abc():
    raw = (
        "ANNEX VIII\n"
        "Information to be submitted upon the registration...\n"
        "Section A — Information to be submitted by providers...\n"
        "1. A item one\n"
        "2. A item two\n"
        "Section B — Information to be submitted by providers...\n"
        "1. B item one\n"
        "Section C — Information to be submitted by deployers...\n"
        "1. C item one\n"
        "5. C item five\n"
    )
    rules = parse_rules(raw)
    # Родитель
    assert any(r["section_code"] == "AnnexVIII" and r["content"] for r in rules)
    # Секции и их заголовки
    sec_a = next(r for r in rules if r["section_code"] == "AnnexVIII.A")
    assert sec_a["title"].startswith("Section A")
    assert sec_a["content"].startswith("1. A item one")
    assert "Section A" not in sec_a["content"]

    sec_b = next(r for r in rules if r["section_code"] == "AnnexVIII.B")
    assert sec_b["title"].startswith("Section B")
    assert "Section B" not in sec_b["content"]

    sec_c = next(r for r in rules if r["section_code"] == "AnnexVIII.C")
    assert sec_c["title"].startswith("Section C")
    assert "Section C" not in sec_c["content"]

    # Подпункты в секциях
    assert any(r["section_code"] == "AnnexVIII.A.1" and "A item one" in r["content"] for r in rules)
    assert any(r["section_code"] == "AnnexVIII.B.1" and "B item one" in r["content"] for r in rules)
    assert any(r["section_code"] == "AnnexVIII.C.5" and "C item five" in r["content"] for r in rules)
