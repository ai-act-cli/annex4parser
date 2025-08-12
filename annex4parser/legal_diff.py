# legal_diff.py
"""Юридически осмысленный diff-анализ для регуляторных документов.

Этот модуль предоставляет продвинутые алгоритмы сравнения юридических текстов,
включая семантический анализ изменений и классификацию их важности.
"""

import difflib
import logging
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LegalChange:
    """Структура для описания юридического изменения."""
    section_code: str
    change_type: str  # "addition", "deletion", "modification", "clarification"
    severity: str     # "major", "minor", "clarification"
    old_text: Optional[str]
    new_text: Optional[str]
    diff_score: float
    semantic_score: float
    keywords_affected: List[str]


class LegalDiffAnalyzer:
    """Анализатор юридических изменений с семантическим анализом."""
    
    def __init__(self):
        # Ключевые слова для определения важности изменений
        self.critical_keywords = {
            "shall", "must", "required", "obligatory", "mandatory",
            "prohibited", "forbidden", "illegal", "criminal",
            "penalty", "fine", "sanction", "liability",
            "risk", "safety", "security", "privacy", "data protection"
        }
        
        self.important_keywords = {
            "may", "should", "recommended", "guidance", "best practice",
            "documentation", "record", "log", "audit", "compliance",
            "assessment", "evaluation", "monitoring", "supervision"
        }
        
        # Инициализируем TF-IDF для семантического анализа
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),
            max_features=1000
        )
    
    def analyze_changes(
        self, 
        old_text: str, 
        new_text: str,
        section_code: str = "unknown"
    ) -> LegalChange:
        """Анализировать изменения между двумя версиями текста.
        
        Parameters
        ----------
        old_text : str
            Старая версия текста
        new_text : str
            Новая версия текста
        section_code : str
            Код секции (например, "Article11")
            
        Returns
        -------
        LegalChange
            Структура с анализом изменений
        """
        # Базовый diff
        diff = self._compute_unified_diff(old_text, new_text)
        
        # Определяем тип изменения
        change_type = self._classify_change_type(diff, old_text, new_text)
        
        # Вычисляем diff score
        diff_score = self._compute_diff_score(diff)
        
        # Семантический анализ
        semantic_score = self._compute_semantic_similarity(old_text, new_text)
        
        # Анализируем затронутые ключевые слова
        keywords_affected = self._find_affected_keywords(old_text, new_text)
        
        # Определяем серьёзность
        severity = self._classify_severity(
            diff_score, semantic_score, keywords_affected, change_type
        )
        
        return LegalChange(
            section_code=section_code,
            change_type=change_type,
            severity=severity,
            old_text=old_text,
            new_text=new_text,
            diff_score=diff_score,
            semantic_score=semantic_score,
            keywords_affected=keywords_affected
        )
    
    def _compute_unified_diff(self, old_text: str, new_text: str) -> str:
        """Вычислить unified diff между текстами."""
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        diff = difflib.ndiff(old_lines, new_lines)
        return "\n".join(diff)
    
    def _classify_change_type(self, diff: str, old_text: str = "", new_text: str = "") -> str:
        """Классифицировать тип изменения на основе diff."""
        added_lines = [line for line in diff.splitlines() 
                      if line.startswith("+ ")]
        removed_lines = [line for line in diff.splitlines() 
                        if line.startswith("- ")]
        
        # Если нет изменений
        if not added_lines and not removed_lines:
            return "no_change"
        
        # Анализируем содержимое для определения типа
        if added_lines and removed_lines:
            # Проверяем, является ли это расширением существующего текста
            for added_line in added_lines:
                added_content = added_line[2:]  # Убираем "+ "
                for removed_line in removed_lines:
                    removed_content = removed_line[2:]  # Убираем "- "
                    if removed_content in added_content:
                        return "addition"  # Старый текст содержится в новом
                    elif added_content in removed_content:
                        return "deletion"  # Новый текст содержится в старом
                    # Проверяем, является ли это добавлением к существующему тексту
                    elif len(added_content) > len(removed_content) and (removed_content in added_content or added_content.startswith(removed_content)):
                        return "addition"  # Новый текст начинается со старого и добавляет что-то
            return "modification"
        
        # Если есть только добавления
        if added_lines and not removed_lines:
            return "addition"
        
        # Если есть только удаления
        if removed_lines and not added_lines:
            return "deletion"
        
        # По умолчанию
        return "clarification"
    
    def _compute_diff_score(self, diff: str) -> float:
        """Вычислить числовую оценку изменений."""
        added_chars = sum(len(line) for line in diff.splitlines() 
                         if line.startswith("+ "))
        removed_chars = sum(len(line) for line in diff.splitlines() 
                           if line.startswith("- "))
        
        total_changes = added_chars + removed_chars
        if total_changes == 0:
            return 0.0
        return min(total_changes / 100.0, 1.0)  # Нормализуем к 0-1
    
    def _compute_semantic_similarity(self, old_text: str, new_text: str) -> float:
        """Вычислить семантическое сходство между текстами."""
        if not old_text.strip() or not new_text.strip():
            return 0.0
        
        try:
            # Векторизуем тексты
            texts = [old_text, new_text]
            tfidf_matrix = self.vectorizer.fit_transform(texts)
            
            # Вычисляем косинусное сходство
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return float(similarity)
        except Exception as e:
            logger.warning(f"Failed to compute semantic similarity: {e}")
            return 0.5  # Fallback
    
    def _find_affected_keywords(self, old_text: str, new_text: str) -> List[str]:
        """Найти ключевые слова, затронутые изменениями."""
        all_keywords = self.critical_keywords | self.important_keywords
        
        affected = []
        for keyword in all_keywords:
            old_count = len(re.findall(rf'\b{re.escape(keyword)}\b', old_text, re.IGNORECASE))
            new_count = len(re.findall(rf'\b{re.escape(keyword)}\b', new_text, re.IGNORECASE))
            
            if old_count != new_count:
                affected.append(keyword)
        
        return affected
    
    def _classify_severity(
        self, 
        diff_score: float, 
        semantic_score: float,
        keywords_affected: List[str],
        change_type: str
    ) -> str:
        """Классифицировать серьёзность изменения."""
        # Критические ключевые слова сильно влияют на серьёзность
        critical_keywords = [kw for kw in keywords_affected if kw in self.critical_keywords]
        
        if critical_keywords:
            return "high"
        
        # Для незначительных изменений (уточнения) возвращаем low
        if change_type == "clarification":
            return "low"
        
        # Почти идентичные тексты при малом diff считаем незначительными
        if semantic_score > 0.9 and diff_score <= 0.10:
            return "low"

        # Высокий diff score или низкое семантическое сходство
        if diff_score > 0.4 or semantic_score < 0.6:
            return "high"

        # Средние изменения
        if diff_score > 0.15 or semantic_score < 0.85:
            return "medium"

        # Незначительные изменения
        return "low"
    
    def get_change_summary(self, change: LegalChange) -> str:
        """Получить краткое описание изменения."""
        summary_parts = []
        
        if change.change_type == "addition":
            summary_parts.append("Добавлен новый текст")
        elif change.change_type == "deletion":
            summary_parts.append("Удалён текст")
        elif change.change_type == "modification":
            summary_parts.append("Изменён существующий текст")
        else:
            summary_parts.append("Уточнение формулировок")
        
        if change.keywords_affected:
            summary_parts.append(f"Затронуты ключевые слова: {', '.join(change.keywords_affected[:3])}")
        
        summary_parts.append(f"Серьёзность: {change.severity}")
        summary_parts.append(f"Семантическое сходство: {change.semantic_score:.2f}")
        
        return ". ".join(summary_parts)


# Удобные функции
def diff_score(old_text: str, new_text: str) -> float:
    """Вычислить diff score между текстами."""
    analyzer = LegalDiffAnalyzer()
    diff = analyzer._compute_unified_diff(old_text, new_text)
    return analyzer._compute_diff_score(diff)


def classify_change(old_text: str, new_text: str) -> str:
    """Классифицировать изменение как addition/deletion/modification/clarification."""
    analyzer = LegalDiffAnalyzer()
    change = analyzer.analyze_changes(old_text, new_text)
    return change.change_type


def analyze_legal_changes(
    old_text: str, 
    new_text: str, 
    section_code: str = "unknown"
) -> LegalChange:
    """Полный анализ юридических изменений."""
    analyzer = LegalDiffAnalyzer()
    return analyzer.analyze_changes(old_text, new_text, section_code)


# Примеры использования
if __name__ == "__main__":
    # Тестовые тексты
    old_text = """
    Article 11 Documentation requirements
    
    Providers shall establish and maintain technical documentation 
    for high-risk AI systems in accordance with this Regulation.
    """
    
    new_text = """
    Article 11 Documentation requirements
    
    Providers shall establish and maintain comprehensive technical documentation 
    for high-risk AI systems in accordance with this Regulation, including 
    detailed risk assessments and mitigation strategies.
    """
    
    # Анализируем изменения
    analyzer = LegalDiffAnalyzer()
    change = analyzer.analyze_changes(old_text, new_text, "Article11")
    
    print(f"Тип изменения: {change.change_type}")
    print(f"Серьёзность: {change.severity}")
    print(f"Затронутые ключевые слова: {change.keywords_affected}")
    print(f"Семантическое сходство: {change.semantic_score:.2f}")
    print(f"Описание: {analyzer.get_change_summary(change)}")
