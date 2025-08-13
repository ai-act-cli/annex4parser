"""Тесты для парсинга Annex IV с иерархией."""

import pytest
from annex4parser.regulation_monitor import parse_rules


class TestAnnexParsing:
    """Тесты для парсинга Annex с иерархией."""

    def test_parse_simple_annex(self):
        """Тест парсинга простого Annex без подразделов."""
        text = """
        ANNEX IV Technical documentation referred to in Article 11(1)

        This annex describes the technical documentation requirements.
        """
        
        rules = parse_rules(text)
        
        # Должен найти один корневой Annex
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        assert len(annex_rules) == 1
        assert annex_rules[0]['section_code'] == 'AnnexIV'
        assert 'Technical documentation' in annex_rules[0]['title']
        assert 'parent_section_code' not in annex_rules[0]

    def test_parse_annex_title_after_blank_line(self):
        """Парсер должен извлекать заголовок, расположенный на новой строке."""
        text = """
        ANNEX IV

        Technical documentation
        1. First point
        """

        rules = parse_rules(text)
        root = next(r for r in rules if r['section_code'] == 'AnnexIV')
        assert root['title'] == 'Technical documentation'
        assert 'First point' in root['content']

    def test_parse_annex_with_numbered_sections(self):
        """Тест парсинга Annex с пронумерованными подразделами."""
        text = """
        ANNEX IV Technical documentation referred to in Article 11(1)

        The technical documentation shall contain:

        1. A general description of the AI system including:
           Some content for section 1.

        2. A detailed description of the elements including:
           Some content for section 2.
        """
        
        rules = parse_rules(text)
        
        # Ищем все правила Annex
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        # Должно быть 3 правила: корневое + 2 подраздела
        assert len(annex_rules) == 3
        
        # Проверяем корневое правило
        root = next(r for r in annex_rules if r['section_code'] == 'AnnexIV')
        assert 'parent_section_code' not in root
        
        # Проверяем подразделы
        section_1 = next(r for r in annex_rules if r['section_code'] == 'AnnexIV.1')
        section_2 = next(r for r in annex_rules if r['section_code'] == 'AnnexIV.2')
        
        assert section_1['parent_section_code'] == 'AnnexIV'
        assert section_2['parent_section_code'] == 'AnnexIV'

    def test_parse_annex_with_lettered_subsections(self):
        """Тест парсинга Annex с буквенными подпунктами."""
        text = """
        ANNEX IV Technical documentation referred to in Article 11(1)

        1. A general description of the AI system including:
           (a) its intended purpose and the person developing the provider;
           (b) how the AI system interacts with hardware or software;

        2. A detailed description including:
           (a) the methods and steps for development;
           (b) the design specifications of the system;
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        # Должно быть 7 правил: корневое + 2 раздела + 4 подпункта
        assert len(annex_rules) == 7
        
        # Проверяем иерархию
        root = next(r for r in annex_rules if r['section_code'] == 'AnnexIV')
        section_1 = next(r for r in annex_rules if r['section_code'] == 'AnnexIV.1')
        section_1a = next(r for r in annex_rules if r['section_code'] == 'AnnexIV.1.a')
        section_1b = next(r for r in annex_rules if r['section_code'] == 'AnnexIV.1.b')
        
        assert 'parent_section_code' not in root
        assert section_1['parent_section_code'] == 'AnnexIV'
        assert section_1a['parent_section_code'] == 'AnnexIV.1'
        assert section_1b['parent_section_code'] == 'AnnexIV.1'

    def test_parse_multiple_annexes(self):
        """Тест парсинга нескольких Annex."""
        text = """
        ANNEX IV Technical documentation

        Content for Annex IV.

        ANNEX VII Conformity assessment

        Content for Annex VII.
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        assert len(annex_rules) == 2
        assert any(r['section_code'] == 'AnnexIV' for r in annex_rules)
        assert any(r['section_code'] == 'AnnexVII' for r in annex_rules)

    def test_parse_articles_and_annexes_together(self):
        """Тест парсинга Articles и Annexes вместе."""
        text = """
        Article 9 Risk management system

        1. Providers shall establish a risk management system.

        Article 15 Documentation requirements

        1. Providers shall maintain documentation.

        ANNEX IV Technical documentation

        1. General description:
           (a) intended purpose;
           (b) system interactions;
        """
        
        rules = parse_rules(text)
        
        # Проверяем Articles
        article_rules = [r for r in rules if r['section_code'].startswith('Article')]
        assert len(article_rules) == 4  # Article9, Article9.1, Article15, Article15.1
        assert any(r['section_code'] == 'Article9' for r in article_rules)
        assert any(r['section_code'] == 'Article15' for r in article_rules)
        
        # Проверяем Annexes
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        assert len(annex_rules) == 4  # AnnexIV + AnnexIV.1 + AnnexIV.1.a + AnnexIV.1.b

    def test_parse_annex_with_roman_numerals(self):
        """Тест парсинга различных римских цифр в Annex."""
        text = """
        ANNEX I High-risk AI systems

        Content for Annex I.

        ANNEX II Prohibited AI practices

        Content for Annex II.

        ANNEX XII CE marking

        Content for Annex XII.
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        assert len(annex_rules) == 3
        codes = {r['section_code'] for r in annex_rules}
        assert codes == {'AnnexI', 'AnnexII', 'AnnexXII'}

    def test_parse_annex_case_insensitive(self):
        """Тест парсинга Annex в разном регистре."""
        text = """
        annex iv Technical documentation

        Content in lowercase.

        ANNEX V Conformity assessment

        Content in uppercase.
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        assert len(annex_rules) == 2
        codes = {r['section_code'] for r in annex_rules}
        assert codes == {'AnnexIV', 'AnnexV'}

    def test_parse_annex_content_extraction(self):
        """Тест извлечения содержимого разделов Annex."""
        text = """
        ANNEX IV Technical documentation referred to in Article 11(1)

        The technical documentation shall contain at least:

        1. A general description including:
           (a) intended purpose and provider details;
           Content for 1.a with multiple lines
           and more details.
           (b) system interactions and interfaces;
           Content for 1.b section.
        """
        
        rules = parse_rules(text)
        
        # Проверяем содержимое подпункта 1.a
        section_1a = next(r for r in rules if r['section_code'] == 'AnnexIV.1.a')
        assert section_1a['title'] is None
        assert 'multiple lines' in section_1a['content']

        # Проверяем содержимое подпункта 1.b
        section_1b = next(r for r in rules if r['section_code'] == 'AnnexIV.1.b')
        assert section_1b['title'] is None
        assert 'Content for 1.b' in section_1b['content']


class TestAnnexParsingEdgeCases:
    """Тесты крайних случаев для парсинга Annex."""

    def test_parse_empty_annex(self):
        """Тест парсинга пустого Annex."""
        text = """
        ANNEX IV Technical documentation

        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        assert len(annex_rules) == 1
        assert annex_rules[0]['section_code'] == 'AnnexIV'
        assert annex_rules[0]['content'].strip() == ''

    def test_parse_annex_without_numbered_sections(self):
        """Тест парсинга Annex без пронумерованных разделов."""
        text = """
        ANNEX IV Technical documentation

        This is just plain text without numbered sections.
        It should be parsed as a single root element.
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        assert len(annex_rules) == 1
        assert annex_rules[0]['section_code'] == 'AnnexIV'
        assert 'plain text' in annex_rules[0]['content']

    def test_parse_annex_malformed_numbering(self):
        """Тест парсинга Annex с неправильной нумерацией."""
        text = """
        ANNEX IV Technical documentation

        1. First section
        3. Third section (skipped 2)
        1. Duplicate first section
        """
        
        rules = parse_rules(text)
        annex_rules = [r for r in rules if r['section_code'].startswith('Annex')]
        
        # Должен парсить все разделы, даже с неправильной нумерацией
        section_codes = {r['section_code'] for r in annex_rules}
        assert 'AnnexIV' in section_codes
        assert 'AnnexIV.1' in section_codes
        assert 'AnnexIV.3' in section_codes
