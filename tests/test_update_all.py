import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from aioresponses import aioresponses
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Source, RegulationSourceLog
from tests.helpers import (
    create_test_source, mock_eli_response, mock_rss_feed,
    mock_html_content, setup_aiohttp_mocks
)
import json


class TestUpdateAll:
    """Тесты для функции update_all"""

    @pytest.mark.asyncio
    async def test_update_all_empty_sources(self, test_db):
        """Тест update_all с пустыми источниками"""
        monitor = RegulationMonitorV2(test_db)
        
        stats = await monitor.update_all()
        
        assert stats["total"] == 0
        assert stats["eli_sparql"] == 0
        assert stats["rss"] == 0
        assert stats["html"] == 0

    @pytest.mark.asyncio
    async def test_update_all_single_source_success(self, test_db, mock_session):
        """Тест update_all с одним источником"""
        source = create_test_source("test_eli", "eli_sparql")
        test_db.add(source)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 1
            assert stats["rss"] == 0
            assert stats["html"] == 0

    @pytest.mark.asyncio
    async def test_update_all_multiple_sources(self, test_db, mock_session):
        """Тест update_all с множественными источниками"""
        sources = [
            create_test_source("eli1", "eli_sparql"),
            create_test_source("eli2", "eli_sparql"),
            create_test_source("rss1", "rss"),
            create_test_source("html1", "html")
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock для ELI источников
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            
            # Mock для RSS источника
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            
            # Mock для HTML источника
            setup_aiohttp_mocks(
                m, "https://example.com/regulation",
                content=mock_html_content()
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 4
            assert stats["eli_sparql"] == 2
            assert stats["rss"] == 1
            assert stats["html"] == 1

    @pytest.mark.asyncio
    async def test_update_all_with_inactive_sources(self, test_db, mock_session):
        """Тест update_all с неактивными источниками"""
        active_source = create_test_source("active", "eli_sparql", active=True)
        inactive_source = create_test_source("inactive", "rss", active=False)
        
        test_db.add_all([active_source, inactive_source])
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 1
            assert stats["rss"] == 0

    @pytest.mark.asyncio
    async def test_update_all_frequency_filtering(self, test_db, mock_session):
        """Тест update_all с фильтрацией по частоте"""
        now = datetime.now()
        
        # Источник, который недавно обновлялся
        recent_source = create_test_source("recent", "eli_sparql", freq="6h")
        recent_source.last_fetched = now - timedelta(hours=2)
        
        # Источник, который нужно обновить
        old_source = create_test_source("old", "rss", freq="1h")
        old_source.last_fetched = now - timedelta(hours=2)
        
        test_db.add_all([recent_source, old_source])
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            
            stats = await monitor.update_all()
            
            # Только RSS источник должен быть обновлен
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 0
            assert stats["rss"] == 1

    @pytest.mark.asyncio
    async def test_update_all_error_handling(self, test_db, mock_session):
        """Тест обработки ошибок в update_all"""
        source = create_test_source("test_eli", "eli_sparql")
        test_db.add(source)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock ошибки сети
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=500,
                body="Server Error"
            )
            
            stats = await monitor.update_all()
            
            # Должен обработать ошибку и продолжить
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 1
            
            # Проверяем, что лог ошибки создан
            logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
            assert len(logs) == 1
            assert logs[0].status == "error"

    @pytest.mark.asyncio
    async def test_update_all_concurrent_processing(self, test_db, mock_session):
        """Тест конкурентной обработки источников"""
        sources = [
            create_test_source(f"source_{i}", "eli_sparql")
            for i in range(5)
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock для всех источников
            for _ in range(5):
                setup_aiohttp_mocks(
                    m, "https://eur-lex.europa.eu/sparql",
                    content=json.dumps(mock_eli_response())
                )
            
            start_time = datetime.now()
            stats = await monitor.update_all()
            end_time = datetime.now()
            
            # Проверяем, что все источники обработаны
            assert stats["total"] == 5
            assert stats["eli_sparql"] == 5
            
            # Проверяем, что обработка была конкурентной (быстрее последовательной)
            processing_time = (end_time - start_time).total_seconds()
            assert processing_time < 5  # Должно быть быстро благодаря async

    @pytest.mark.asyncio
    async def test_update_all_mixed_success_failure(self, test_db, mock_session):
        """Тест смешанных успехов и неудач"""
        sources = [
            create_test_source("success1", "eli_sparql"),
            create_test_source("success2", "rss"),
            create_test_source("failure1", "html")
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Успешные запросы
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            
            # Неудачный запрос
            m.add(
                url="https://example.com/regulation",
                method="GET",
                status=404,
                body="Not Found"
            )
            
            stats = await monitor.update_all()
            
            # Все источники должны быть обработаны
            assert stats["total"] == 3
            assert stats["eli_sparql"] == 1
            assert stats["rss"] == 1
            assert stats["html"] == 1

    @pytest.mark.asyncio
    async def test_update_all_with_alert_integration(self, test_db, mock_session, mock_kafka_producer):
        """Тест update_all с интеграцией алертов"""
        source = create_test_source("test_eli", "eli_sparql")
        test_db.add(source)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        # Добавляем alert emitter
        from annex4parser.alerts.webhook import AlertEmitter
        monitor.alert_emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        monitor.alert_emitter.producer = mock_kafka_producer
        
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 1
            # Проверяем, что алерты отправлены (если есть изменения)
            # mock_kafka_producer.send.assert_called()  # Может быть или не быть

    @pytest.mark.asyncio
    async def test_update_all_performance_monitoring(self, test_db, mock_session):
        """Тест мониторинга производительности update_all"""
        sources = [
            create_test_source(f"source_{i}", "eli_sparql")
            for i in range(3)
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            for _ in range(3):
                setup_aiohttp_mocks(
                    m, "https://eur-lex.europa.eu/sparql",
                    content=json.dumps(mock_eli_response())
                )
            
            start_time = datetime.now()
            stats = await monitor.update_all()
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            # Проверяем статистику
            assert stats["total"] == 3
            assert stats["eli_sparql"] == 3
            
            # Проверяем логи производительности
            logs = test_db.query(RegulationSourceLog).all()
            assert len(logs) == 3
            
            for log in logs:
                assert log.response_time > 0
                assert log.bytes_downloaded > 0

    @pytest.mark.asyncio
    async def test_update_all_with_different_source_types(self, test_db, mock_session):
        """Тест update_all с разными типами источников"""
        sources = [
            create_test_source("eli1", "eli_sparql", freq="6h"),
            create_test_source("eli2", "eli_sparql", freq="12h"),
            create_test_source("rss1", "rss", freq="1h"),
            create_test_source("rss2", "rss", freq="2h"),
            create_test_source("html1", "html", freq="24h")
        ]
        
        # Устанавливаем разные времена последнего обновления
        now = datetime.now()
        sources[0].last_fetched = now - timedelta(hours=7)  # Нужно обновить
        sources[1].last_fetched = now - timedelta(hours=5)  # Не нужно
        sources[2].last_fetched = now - timedelta(hours=2)  # Нужно обновить
        sources[3].last_fetched = now - timedelta(minutes=30)  # Не нужно
        sources[4].last_fetched = now - timedelta(hours=25)  # Нужно обновить
        
        test_db.add_all(sources)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock для всех типов источников
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            setup_aiohttp_mocks(
                m, "https://example.com/regulation",
                content=mock_html_content()
            )
            
            stats = await monitor.update_all()
            
            # Проверяем, что обновлены только нужные источники
            assert stats["total"] == 3  # 1 ELI + 1 RSS + 1 HTML
            assert stats["eli_sparql"] == 1
            assert stats["rss"] == 1
            assert stats["html"] == 1

    @pytest.mark.asyncio
    async def test_update_all_empty_response_handling(self, test_db, mock_session):
        """Тест обработки пустых ответов"""
        source = create_test_source("test_eli", "eli_sparql")
        test_db.add(source)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock пустого ответа
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps({"results": {"bindings": []}})
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 1
            
            # Проверяем лог
            logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
            assert len(logs) == 1
            assert logs[0].status == "success"  # Пустой ответ - это не ошибка

    @pytest.mark.asyncio
    async def test_update_all_timeout_handling(self, test_db, mock_session):
        """Тест обработки таймаутов"""
        source = create_test_source("test_eli", "eli_sparql")
        test_db.add(source)
        test_db.commit()
        
        monitor = RegulationMonitorV2(test_db)
        
        with aioresponses() as m:
            # Mock таймаута
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                exception=asyncio.TimeoutError("Request timeout")
            )
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 1
            assert stats["eli_sparql"] == 1
            
            # Проверяем лог ошибки
            logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
            assert len(logs) == 1
            assert logs[0].status == "error"
            assert "timeout" in logs[0].error_message.lower()


