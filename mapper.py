# mapper.py
import re
from collections import defaultdict
from .models import DocumentRuleMapping

# Простейшая матрица ключевых слов → код статьи
KEYWORD_MAP = {
    'risk management': 'Article9.2',
    'data governance': 'Article10.1',
    'documentation': 'Article15.3',
    'record keeping': 'Article15.4',
    'accuracy': 'Article16.1',
}

def match_rules(doc_text: str) -> dict[str, float]:
    """
    Ищет ключевые слова в тексте документа и возвращает словарь:
    {код правила: confidence_score}. Для MVP confidence = 0.8 при находке.
    """
    result = defaultdict(float)
    for keyword, rule_code in KEYWORD_MAP.items():
        if re.search(rf'\b{re.escape(keyword)}\b', doc_text, re.IGNORECASE):
            result[rule_code] = max(result[rule_code], 0.8)
    return result
