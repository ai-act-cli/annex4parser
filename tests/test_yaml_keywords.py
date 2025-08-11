"""Тесты для гибкого keyword mapping через YAML."""

import os
import tempfile
import pytest
from pathlib import Path
from annex4parser.mapper.mapper import match_rules, _load_keywords_from_yaml


class TestYAMLKeywordMapping:
    """Тесты для загрузки ключевых слов из YAML."""

    def test_load_keywords_from_yaml_file(self):
        """Тест загрузки ключевых слов из YAML файла."""
        # Создаем временный YAML файл
        yaml_content = """
technical documentation: AnnexIV
risk assessment: Article9.2
human oversight: Article14
conformity assessment: AnnexIV.1
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            # Устанавливаем переменную окружения
            old_env = os.environ.get('ANNEX4_KEYWORDS')
            os.environ['ANNEX4_KEYWORDS'] = yaml_path
            
            # Загружаем ключевые слова
            keywords = _load_keywords_from_yaml()
            
            assert 'technical documentation' in keywords
            assert keywords['technical documentation'] == 'AnnexIV'
            assert keywords['risk assessment'] == 'Article9.2'
            assert keywords['human oversight'] == 'Article14'
            assert keywords['conformity assessment'] == 'AnnexIV.1'
            
        finally:
            # Очищаем
            os.unlink(yaml_path)
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']

    def test_load_keywords_fallback_to_default(self):
        """Тест возврата к DEFAULT_KEYWORD_MAP если YAML не найден."""
        # Устанавливаем несуществующий путь
        old_env = os.environ.get('ANNEX4_KEYWORDS')
        os.environ['ANNEX4_KEYWORDS'] = '/nonexistent/path.yaml'
        
        try:
            keywords = _load_keywords_from_yaml()
            # Должен вернуть пустой словарь (будет использован DEFAULT_KEYWORD_MAP)
            assert keywords == {}
        finally:
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']

    def test_yaml_keywords_override_default(self):
        """Тест переопределения ключевых слов через YAML."""
        # Создаем YAML с переопределением
        yaml_content = """
documentation: AnnexIV
risk management: Article9.2
new keyword: AnnexIV.1.a
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            old_env = os.environ.get('ANNEX4_KEYWORDS')
            os.environ['ANNEX4_KEYWORDS'] = yaml_path
            
            # Принудительно перезагружаем модуль
            import sys
            if 'annex4parser.mapper.mapper' in sys.modules:
                del sys.modules['annex4parser.mapper.mapper']
            if 'annex4parser.mapper' in sys.modules:
                del sys.modules['annex4parser.mapper']
            
            # Импортируем заново
            from annex4parser.mapper.mapper import match_rules, _load_keywords_from_yaml
            
            # Проверяем что YAML загружается правильно
            loaded_keywords = _load_keywords_from_yaml()
            
            # Тестируем маппинг
            test_text = "This document covers documentation and new keyword requirements."
            matches = match_rules(test_text)
            
            # Проверяем что переопределение работает
            assert 'AnnexIV' in matches, f"Expected 'AnnexIV' in matches, got: {matches}"
            assert 'AnnexIV.1.a' in matches, f"Expected 'AnnexIV.1.a' in matches, got: {matches}"
            
        finally:
            os.unlink(yaml_path)
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']
            
            # Перезагружаем модуль с оригинальными настройками
            import sys
            if 'annex4parser.mapper.mapper' in sys.modules:
                del sys.modules['annex4parser.mapper.mapper']
            if 'annex4parser.mapper' in sys.modules:
                del sys.modules['annex4parser.mapper']

    def test_yaml_with_annex_keywords(self):
        """Тест YAML с ключевыми словами для Annex IV."""
        yaml_content = """
technical documentation: AnnexIV
post-market monitoring plan: AnnexIV.3
conformity assessment: AnnexIV.1
ce marking: AnnexIV.1.a
system architecture: AnnexIV.2.a
dataset description: AnnexIV.2.b
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            old_env = os.environ.get('ANNEX4_KEYWORDS')
            os.environ['ANNEX4_KEYWORDS'] = yaml_path
            
            import importlib
            from annex4parser.mapper import mapper
            importlib.reload(mapper)
            
            # Тестируем различные тексты
            test_cases = [
                ("The technical documentation must include system architecture", 
                 {'AnnexIV', 'AnnexIV.2.a'}),
                ("CE marking and conformity assessment procedures", 
                 {'AnnexIV.1.a', 'AnnexIV.1'}),
                ("Dataset description for post-market monitoring plan", 
                 {'AnnexIV.2.b', 'AnnexIV.3'}),
            ]
            
            for text, expected_codes in test_cases:
                matches = mapper.match_rules(text)
                matched_codes = set(matches.keys())
                assert expected_codes.issubset(matched_codes), f"Expected {expected_codes} in {matched_codes} for text: {text}"
            
        finally:
            os.unlink(yaml_path)
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']
            
            import importlib
            from annex4parser.mapper import mapper
            importlib.reload(mapper)

    def test_yaml_malformed_content(self):
        """Тест обработки неправильного YAML."""
        yaml_content = """
invalid: yaml: content:
  - with
  - malformed: structure
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            old_env = os.environ.get('ANNEX4_KEYWORDS')
            os.environ['ANNEX4_KEYWORDS'] = yaml_path
            
            # Должен вернуть пустой словарь при ошибке парсинга
            keywords = _load_keywords_from_yaml()
            assert keywords == {}
            
        finally:
            os.unlink(yaml_path)
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']

    def test_yaml_case_normalization(self):
        """Тест нормализации регистра ключевых слов."""
        yaml_content = """
Technical Documentation: AnnexIV
RISK ASSESSMENT: Article9.2
Human Oversight: Article14
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            old_env = os.environ.get('ANNEX4_KEYWORDS')
            os.environ['ANNEX4_KEYWORDS'] = yaml_path
            
            keywords = _load_keywords_from_yaml()
            
            # Все ключи должны быть в нижнем регистре
            assert 'technical documentation' in keywords
            assert 'risk assessment' in keywords
            assert 'human oversight' in keywords
            
            # Значения должны остаться как есть
            assert keywords['technical documentation'] == 'AnnexIV'
            assert keywords['risk assessment'] == 'Article9.2'
            
        finally:
            os.unlink(yaml_path)
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            elif 'ANNEX4_KEYWORDS' in os.environ:
                del os.environ['ANNEX4_KEYWORDS']


class TestKeywordMappingIntegration:
    """Интеграционные тесты для keyword mapping."""

    def test_config_keywords_file_exists(self):
        """Тест существования файла config/keywords.yaml."""
        config_path = Path(__file__).parent.parent / "annex4parser" / "config" / "keywords.yaml"
        assert config_path.exists(), f"Config file should exist at {config_path}"
        
        # Проверяем что файл можно загрузить
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        assert isinstance(data, dict)
        assert len(data) > 0
        
        # Проверяем что есть Annex IV ключевые слова
        annex_keywords = [v for v in data.values() if 'Annex' in v]
        assert len(annex_keywords) > 0

    def test_default_config_keywords_loading(self):
        """Тест загрузки ключевых слов из config файла по умолчанию."""
        # Убираем переменную окружения чтобы использовался default путь
        old_env = os.environ.get('ANNEX4_KEYWORDS')
        if 'ANNEX4_KEYWORDS' in os.environ:
            del os.environ['ANNEX4_KEYWORDS']
        
        try:
            import importlib
            from annex4parser.mapper import mapper
            importlib.reload(mapper)
            
            # Тестируем что ключевые слова из config файла работают
            test_text = "This document covers technical documentation and conformity assessment."
            matches = mapper.match_rules(test_text)
            
            # Должны найти маппинги из config файла
            assert len(matches) > 0
            
        finally:
            if old_env is not None:
                os.environ['ANNEX4_KEYWORDS'] = old_env
            
            import importlib
            from annex4parser.mapper import mapper
            importlib.reload(mapper)
