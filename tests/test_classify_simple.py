import pytest
from annex4parser.legal_diff import LegalDiffAnalyzer


def test_classify_change_tiers():
    """Тест классификации изменений по уровням"""
    analyzer = LegalDiffAnalyzer()
    
    # Малое изменение
    small = analyzer.analyze_changes("abc", "abcd", "Test")
    assert small.change_type in ["clarification", "addition"]

    # Среднее изменение
    medium = analyzer.analyze_changes("a"*50, "b"*200, "Test")   # 150 chars diff
    assert medium.change_type == "modification"

    # Большое изменение
    big = analyzer.analyze_changes("a"*10, "b"*600, "Test")      # >500
    assert big.change_type in ["addition", "modification"]
