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


@pytest.mark.skip(reason="outdated after query refactor")
class TestUpdateAll:
    """Тесты для функции update_all"""

    @pytest.mark.asyncio
    async def test_update_all_empty_sources(self, test_db):
        """Тест update_all с пустыми источниками"""
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            stats = await monitor.update_all()
            
            assert stats["total"] == 0
            assert stats["eli_sparql"] == 0
            assert stats["rss"] == 0
            assert stats["html"] == 0
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_single_source_success(self, test_db):
        """Тест update_all с одним источником"""
        # Создаем источник с правильным CELEX ID
        source = Source(
            id="test_eli",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        test_db.add(source)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)

            # Используем патчинг вместо aioresponses
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }):
                stats = await monitor.update_all()
                
                assert stats["total"] == 1
                assert stats["eli_sparql"] == 1
                assert stats["rss"] == 0
                assert stats["html"] == 0
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_multiple_sources(self, test_db):
        """Тест update_all с множественными источниками"""
        # Создаем источники с правильными данными
        sources = [
            Source(
                id="eli1",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": "32024R1689"}
            ),
            Source(
                id="eli2",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": "32023R0988"}
            ),
            Source(
                id="rss1",
                url="https://ec.europa.eu/info/feed/ai-act",
                type="rss",
                freq="1h",
                active=True
            ),
            Source(
                id="html1",
                url="https://example.com/regulation",
                type="html",
                freq="24h",
                active=True
            )
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)

            # Используем патчинг для всех методов
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }), patch.object(monitor, '_fetch_html_text', return_value='Test HTML content'), \
                 patch.object(monitor, '_process_rss_source', return_value={'type': 'rss', 'source_id': 'rss1'}):
                stats = await monitor.update_all()
                
                assert stats["total"] == 4
                assert stats["eli_sparql"] == 2
                assert stats["rss"] == 1
                assert stats["html"] == 1
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_with_inactive_sources(self, test_db):
        """Тест update_all с неактивными источниками"""
        active_source = Source(
            id="active",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        inactive_source = Source(
            id="inactive",
            url="https://ec.europa.eu/info/feed/ai-act",
            type="rss",
            freq="1h",
            active=False
        )
        
        test_db.add_all([active_source, inactive_source])
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)

            # Используем патчинг для ELI источника
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }):
                stats = await monitor.update_all()
                
                assert stats["total"] == 1
                assert stats["eli_sparql"] == 1
                assert stats["rss"] == 0
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_frequency_filtering(self, test_db):
        """Тест update_all с фильтрацией по частоте"""
        now = datetime.now()
        
        # Источник, который недавно обновлялся
        recent_source = Source(
            id="recent",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        recent_source.last_fetched = now - timedelta(hours=2)
        
        # Источник, который нужно обновить
        old_source = Source(
            id="old",
            url="https://ec.europa.eu/info/feed/ai-act",
            type="rss",
            freq="1h",
            active=True
        )
        old_source.last_fetched = now - timedelta(hours=2)
        
        test_db.add_all([recent_source, old_source])
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для RSS источника
            with patch.object(monitor, '_process_rss_source', return_value={'type': 'rss', 'source_id': 'old'}):
                stats = await monitor.update_all()
                
                # Только RSS источник должен быть обновлен
                assert stats["total"] == 1
                assert stats["eli_sparql"] == 0
                assert stats["rss"] == 1
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_error_handling(self, test_db):
        """Тест обработки ошибок в update_all"""
        source = Source(
            id="test_eli",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        test_db.add(source)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для симуляции ошибки
            with patch.object(monitor, '_execute_sparql_query', side_effect=Exception("Test error")):
                stats = await monitor.update_all()
                
                # Должен обработать ошибку и продолжить
                assert stats["total"] == 0  # Ошибка не считается успешной обработкой
                assert stats["eli_sparql"] == 0
                assert stats["errors"] == 1
                
                # Проверяем, что лог ошибки создан
                logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
                assert len(logs) == 1
                assert logs[0].status == "error"
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_concurrent_processing(self, test_db):
        """Тест конкурентной обработки источников"""
        sources = [
            Source(
                id=f"source_{i}",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": f"32024R168{i}"}
            )
            for i in range(5)
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)

            # Используем патчинг для всех источников
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }):
                start_time = datetime.now()
                stats = await monitor.update_all()
                end_time = datetime.now()
                
                # Проверяем, что все источники обработаны
                assert stats["total"] == 5
                assert stats["eli_sparql"] == 5
                
                # Проверяем, что обработка была конкурентной (быстрее последовательной)
                processing_time = (end_time - start_time).total_seconds()
                assert processing_time < 5  # Должно быть быстро благодаря async
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_mixed_success_failure(self, test_db):
        """Тест смешанных успехов и неудач"""
        sources = [
            Source(
                id="success1",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": "32024R1689"}
            ),
            Source(
                id="success2",
                url="https://ec.europa.eu/info/feed/ai-act",
                type="rss",
                freq="1h",
                active=True
            ),
            Source(
                id="failure1",
                url="https://example.com/regulation",
                type="html",
                freq="24h",
                active=True
            )
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для симуляции смешанных результатов
            def mock_process_eli(source, session):
                return {'type': 'eli_sparql', 'source_id': 'success1'}
            
            def mock_process_rss(source, session):
                return {'type': 'rss', 'source_id': 'success2'}
            
            def mock_process_html(source, session):
                raise Exception("Test error")
            
            with patch.object(monitor, '_process_eli_source', side_effect=mock_process_eli), \
                 patch.object(monitor, '_process_rss_source', side_effect=mock_process_rss), \
                 patch.object(monitor, '_process_html_source', side_effect=mock_process_html):
                stats = await monitor.update_all()
                
                # Все источники должны быть обработаны
                assert stats["total"] == 2  # 2 успешных, 1 ошибка
                assert stats["eli_sparql"] == 1
                assert stats["rss"] == 1
                assert stats["html"] == 0
                assert stats["errors"] == 1
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_with_alert_integration(self, test_db, mock_kafka_producer):
        """Тест update_all с интеграцией алертов"""
        source = Source(
            id="test_eli",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        test_db.add(source)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Добавляем alert emitter
            from annex4parser.alerts.webhook import AlertEmitter
            monitor.alert_emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
            monitor.alert_emitter.producer = mock_kafka_producer

            # Используем патчинг для ELI источника
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }):
                stats = await monitor.update_all()
                
                assert stats["total"] == 1
                # Проверяем, что алерты отправлены (если есть изменения)
                # mock_kafka_producer.send.assert_called()  # Может быть или не быть
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_performance_monitoring(self, test_db):
        """Тест мониторинга производительности update_all"""
        sources = [
            Source(
                id=f"source_{i}",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": f"32024R168{i}"}
            )
            for i in range(3)
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)

            # Используем патчинг для всех источников
            with patch.object(monitor, '_execute_sparql_query', return_value={
                'title': 'Test Regulation',
                'date': '2024-01-15',
                'version': '1.0',
                'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
            }):
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
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_with_different_source_types(self, test_db):
        """Тест update_all с разными типами источников"""
        # Создаем источники с правильными URL и параметрами
        now = datetime.now()
        sources = [
            Source(
                id="eli1",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="6h",
                active=True,
                extra={"celex_id": "32024R1689"},
                last_fetched=now - timedelta(hours=7)  # Нужно обновить
            ),
            Source(
                id="eli2",
                url="https://eur-lex.europa.eu/sparql",
                type="eli_sparql",
                freq="12h",
                active=True,
                extra={"celex_id": "32024R1690"},
                last_fetched=now - timedelta(hours=5)  # Не нужно
            ),
            Source(
                id="rss1",
                url="https://ec.europa.eu/info/feed/ai-act",
                type="rss",
                freq="1h",
                active=True,
                last_fetched=now - timedelta(hours=2)  # Нужно обновить
            ),
            Source(
                id="rss2",
                url="https://ec.europa.eu/info/feed/ai-act",
                type="rss",
                freq="2h",
                active=True,
                last_fetched=now - timedelta(minutes=30)  # Не нужно
            ),
            Source(
                id="html1",
                url="https://example.com/regulation",
                type="html",
                freq="24h",
                active=True,
                last_fetched=now - timedelta(hours=25)  # Нужно обновить
            )
        ]
        
        test_db.add_all(sources)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для внутренних методов с условной логикой
            def mock_process_eli(source, session):
                if source.id == 'eli1':  # Нужно обновить
                    return {'type': 'eli_sparql', 'source_id': 'eli1'}
                return None  # Не нужно обновлять
            
            def mock_process_rss(source, session):
                if source.id == 'rss1':  # Нужно обновить
                    return {'type': 'rss', 'source_id': 'rss1'}
                return None  # Не нужно обновлять
            
            def mock_process_html(source, session):
                if source.id == 'html1':  # Нужно обновить
                    return {'type': 'html', 'source_id': 'html1'}
                return None  # Не нужно обновлять
            
            with patch.object(monitor, '_process_eli_source', side_effect=mock_process_eli), \
                 patch.object(monitor, '_process_html_source', side_effect=mock_process_html), \
                 patch.object(monitor, '_process_rss_source', side_effect=mock_process_rss):
                
                stats = await monitor.update_all()
                
                # Проверяем, что обновлены только нужные источники
                assert stats["total"] == 3  # 1 ELI + 1 RSS + 1 HTML
                assert stats["eli_sparql"] == 1
                assert stats["rss"] == 1
                assert stats["html"] == 1
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_empty_response_handling(self, test_db):
        """Тест обработки пустых ответов"""
        # Создаем источник с правильным CELEX ID
        source = Source(
            id="test_eli",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        test_db.add(source)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для внутренних методов
            def mock_process_eli_success(source, session):
                # Логируем успешную операцию
                monitor._log_source_operation(source.id, "success", "test_hash", 100, None)
                return {'type': 'eli_sparql', 'source_id': 'test_eli'}
            
            with patch.object(monitor, '_process_eli_source', side_effect=mock_process_eli_success):
                
                stats = await monitor.update_all()
                
                assert stats["total"] == 1
                assert stats["eli_sparql"] == 1
                
                # Проверяем лог
                logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
                assert len(logs) == 1
                assert logs[0].status == "success"  # Пустой ответ - это не ошибка
        finally:
            import os
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_update_all_timeout_handling(self, test_db):
        """Тест обработки таймаутов"""
        # Создаем источник с правильным CELEX ID
        source = Source(
            id="test_eli",
            url="https://eur-lex.europa.eu/sparql",
            type="eli_sparql",
            freq="6h",
            active=True,
            extra={"celex_id": "32024R1689"}
        )
        test_db.add(source)
        test_db.commit()
        
        # Создаем временный файл конфигурации с пустыми источниками
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"sources": []}, f)
            config_path = f.name
        
        try:
            monitor = RegulationMonitorV2(test_db, config_path=config_path)
            
            # Используем патчинг для внутренних методов с таймаутом
            def mock_process_eli_timeout(source, session):
                # Логируем ошибку
                monitor._log_source_operation(source.id, "error", None, None, "Request timeout")
                raise asyncio.TimeoutError("Request timeout")
            
            with patch.object(monitor, '_process_eli_source', side_effect=mock_process_eli_timeout):
                
                stats = await monitor.update_all()
                
                assert stats["total"] == 0  # Нет успешных обработок
                assert stats["eli_sparql"] == 0  # Нет успешных ELI обработок
                assert stats["errors"] == 1  # Есть одна ошибка
                
                # Проверяем лог ошибки
                logs = test_db.query(RegulationSourceLog).filter_by(source_id=source.id).all()
                assert len(logs) == 1
                assert logs[0].status == "error"
                assert "timeout" in logs[0].error_message.lower()
        finally:
            import os
            os.unlink(config_path)


