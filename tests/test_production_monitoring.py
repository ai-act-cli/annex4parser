# test_production_monitoring.py
"""Тесты для production-grade компонентов мониторинга регуляторов."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from annex4parser.models import Base, Source, RegulationSourceLog
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.eli_client import fetch_latest_eli
from annex4parser.rss_listener import fetch_rss_feed, RSSMonitor
from annex4parser.legal_diff import LegalDiffAnalyzer, analyze_legal_changes
from annex4parser.alerts import AlertEmitter


@pytest.fixture
def test_db():
    """Создаём тестовую базу данных."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


@pytest.fixture
def sample_sources():
    """Тестовые источники."""
    return [
        {
            "id": "test_eli",
            "url": "https://eur-lex.europa.eu/eli-register?uri=eli%3a%2f%2flaw%2fregulation%2f2023%2f988",
            "type": "eli_sparql",
            "freq": "6h"
        },
        {
            "id": "test_rss",
            "url": "https://www.europarl.europa.eu/rss/doc/debates-plenary/en.xml",
            "type": "rss",
            "freq": "instant"
        }
    ]


class TestRegulationMonitorV2:
    """Тесты для RegulationMonitorV2."""
    
    @pytest.mark.asyncio
    async def test_init_sources(self, test_db, sample_sources, test_config_path):
        """Тест инициализации источников."""
        # Мокаем конфигурацию
        config = {"sources": sample_sources}
        
        with patch('annex4parser.regulation_monitor_v2.yaml.safe_load', return_value=config):
            monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
            
            # Проверяем, что источники созданы
            sources = test_db.query(Source).all()
            assert len(sources) >= 2  # Включая источники из конфига
            source_ids = [s.id for s in sources]
            assert "test_eli" in source_ids
            assert "test_rss" in source_ids
    
    @pytest.mark.asyncio
    async def test_update_all_empty(self, test_db, test_config_path):
        """Тест обновления без источников."""
        config = {"sources": []}
        
        with patch('annex4parser.regulation_monitor_v2.yaml.safe_load', return_value=config):
            monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
            stats = await monitor.update_all()
            
            assert stats["eli_sparql"] == 0
            assert stats["rss"] == 0
            assert stats["html"] == 0
            assert stats["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_extract_celex_id(self, test_db, test_config_path):
        """Тест извлечения CELEX ID."""
        config = {"sources": []}
        
        with patch('annex4parser.regulation_monitor_v2.yaml.safe_load', return_value=config):
            monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
            
            # Тестируем извлечение CELEX ID
            url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689"
            celex_id = monitor._extract_celex_id(url)
            assert celex_id == "32024R1689"
            
            # Тестируем URL без CELEX ID
            url_no_celex = "https://example.com"
            celex_id = monitor._extract_celex_id(url_no_celex)
            assert celex_id is None


class TestELIClient:
    """Тесты для ELI SPARQL клиента."""
    
    @pytest.mark.asyncio
    async def test_fetch_latest_eli_success(self):
        """Тест успешного получения данных через ELI."""
        mock_response = {
            "results": {
                "bindings": [{
                    "date": {"value": "2023-12-01"},
                    "version": {"value": "1.0"},
                    "title": {"value": "Test Regulation"},
                    "item": {"value": "http://example.com/doc.pdf"},
                    "format": {"value": "PDF"}
                }]
            }
        }
        
        mock_response_obj = MagicMock()
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_response_obj.raise_for_status = MagicMock()
        # Асинхронный контекстный менеджер
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response_obj
            async def __aexit__(self, exc_type, exc, tb):
                pass
        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManager()
        
        result = await fetch_latest_eli(mock_session, "32023R0988")
        
        assert result is not None
        assert result["title"] == "Test Regulation"
        assert result["version"] == "1.0"
        assert result["items"][0]["url"] == "http://example.com/doc.pdf"
    
    @pytest.mark.asyncio
    async def test_fetch_latest_eli_no_results(self):
        """Тест получения данных без результатов."""
        mock_response = {"results": {"bindings": []}}
        
        mock_response_obj = MagicMock()
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_response_obj.raise_for_status = MagicMock()
        # Асинхронный контекстный менеджер
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_response_obj
            async def __aexit__(self, exc_type, exc, tb):
                pass
        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManager()
        
        result = await fetch_latest_eli(mock_session, "32023R0988")
        
        assert result is None


class TestRSSListener:
    """Тесты для RSS-листенера."""
    
    @pytest.mark.asyncio
    async def test_fetch_rss_success(self):
        """Тест успешного получения RSS-фида."""
        from unittest.mock import MagicMock, AsyncMock, patch
        mock_response_obj = MagicMock()
        mock_response_obj.text = AsyncMock(
            return_value="""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0">
                <channel>
                    <item>
                        <title>Test Entry</title>
                        <link>https://example.com/test</link>
                    </item>
                </channel>
            </rss>
            """
        )
        mock_response_obj.raise_for_status = MagicMock()
        class AsyncGetContextManager:
            async def __aenter__(self):
                return mock_response_obj
            async def __aexit__(self, exc_type, exc, tb):
                pass
        class AsyncSessionContextManager:
            async def __aenter__(self):
                return mock_session
            async def __aexit__(self, exc_type, exc, tb):
                pass
        mock_session = MagicMock()
        mock_session.get.return_value = AsyncGetContextManager()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        with patch('aiohttp.ClientSession', return_value=mock_session):
            entries = await fetch_rss_feed("https://example.com/rss")
            assert len(entries) == 1
            assert entries[0][2] == "Test Entry"  # title
            assert entries[0][0] == "https://example.com/test"  # link
    
    def test_rss_monitor(self):
        """Тест RSS-монитора."""
        monitor = RSSMonitor()
        
        # Симулируем новые элементы
        entries = [
            ("https://example.com/1", "hash1", "Entry 1"),
            ("https://example.com/2", "hash2", "Entry 2")
        ]
        
        # Первый раз - все элементы новые
        new_entries = monitor.check_new_entries(entries)
        assert len(new_entries) == 2
        
        # Второй раз - нет новых элементов
        new_entries = monitor.check_new_entries(entries)
        assert len(new_entries) == 0


class TestLegalDiffAnalyzer:
    """Тесты для юридического diff-анализатора."""
    
    def test_analyze_changes_addition(self):
        """Тест анализа добавления текста."""
        analyzer = LegalDiffAnalyzer()
        
        old_text = "Article 11 Documentation requirements."
        new_text = "Article 11 Documentation requirements. Providers shall maintain records."

        change = analyzer.analyze_changes(old_text, new_text, "Article11")

        assert change.change_type == "addition"
        assert change.severity in ["minor", "major", "high"]
        assert change.section_code == "Article11"
    
    def test_analyze_changes_modification(self):
        """Тест анализа модификации текста."""
        analyzer = LegalDiffAnalyzer()
        
        old_text = "Providers shall maintain documentation."
        new_text = "Providers must maintain comprehensive documentation."
        
        change = analyzer.analyze_changes(old_text, new_text, "Article11")
        
        assert change.change_type == "modification"
        assert "must" in change.keywords_affected  # критическое ключевое слово
        assert change.severity in ["major", "high"]
    
    def test_analyze_changes_clarification(self):
        """Тест анализа уточнений."""
        analyzer = LegalDiffAnalyzer()
        
        old_text = "Providers shall maintain documentation."
        new_text = "Providers shall maintain documentation."
        
        change = analyzer.analyze_changes(old_text, new_text, "Article11")
        
        assert change.severity in ["clarification", "low"]
        assert change.semantic_score > 0.9
    
    def test_classify_change(self):
        """Тест классификации изменений."""
        from annex4parser.legal_diff import classify_change
        
        old_text = "Simple text."
        new_text = "Simple text with additions."
        
        severity = classify_change(old_text, new_text)
        assert severity in ["minor", "major", "clarification", "modification"]


class TestAlertEmitter:
    """Тесты для эмиттера алертов."""
    
    def test_emit_rule_changed(self):
        """Тест эмиссии алерта об изменении правила."""
        emitter = AlertEmitter()
        
        # Мокаем Kafka producer
        mock_producer = Mock()
        emitter.kafka_producer = mock_producer
        
        # Эмитируем алерт
        emitter.emit_rule_changed(
            rule_id="rule-123",
            severity="major",
            regulation_name="EU AI Act",
            section_code="Article11"
        )
        
        # Проверяем, что сообщение отправлено
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        assert call_args[1]["key"] == "rule-123"
    
    def test_emit_rss_update(self):
        """Тест эмиссии RSS-алерта."""
        emitter = AlertEmitter()
        
        # Мокаем Kafka producer
        mock_producer = Mock()
        emitter.kafka_producer = mock_producer
        
        # Эмитируем RSS алерт
        emitter.emit_rss_update(
            source_id="ep_plenary",
            title="New Regulation",
            link="https://example.com"
        )
        
        # Проверяем, что сообщение отправлено
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        assert call_args[1]["key"] == "ep_plenary"


@pytest.mark.asyncio
async def test_integration_workflow(test_db, test_config_path):
    """Интеграционный тест полного workflow."""
    # Создаём тестовые источники
    sources = [
        Source(id="test_eli", url="https://example.com", type="eli_sparql", freq="6h"),
        Source(id="test_rss", url="https://example.com/rss", type="rss", freq="instant")
    ]
    
    for source in sources:
        test_db.add(source)
    test_db.commit()
    
    # Мокаем конфигурацию
    config = {"sources": []}
    
    with patch('annex4parser.regulation_monitor_v2.yaml.safe_load', return_value=config):
        monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
        
        # Мокаем внешние вызовы
        with patch(
            'annex4parser.regulation_monitor_v2.RegulationMonitorV2._execute_sparql_query',
            new_callable=AsyncMock
        ) as mock_sparql, patch(
            'annex4parser.regulation_monitor_v2.fetch_rss_feed',
            new_callable=AsyncMock
        ) as mock_rss:
            mock_sparql.return_value = {
                "title": "Test Regulation",
                "version": "1.0",
                "text": "Article 15.3 Test content."
            }
            mock_rss.return_value = [
                ("https://example.com/1", "hash1", "Test RSS Entry")
            ]
            stats = await monitor.update_all()
            assert stats["eli_sparql"] >= 0
            assert stats["rss"] >= 0
            assert stats["errors"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


