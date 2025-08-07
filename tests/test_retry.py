import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from aioresponses import aioresponses
from tenacity import RetryError, stop_after_attempt, wait_exponential_jitter
from annex4parser.eli_client import fetch_latest_eli
from annex4parser.rss_listener import fetch_rss
from tests.helpers import (
    create_test_source, mock_eli_response, mock_rss_feed,
    setup_aiohttp_mocks, create_retry_test_data
)


class TestRetryMechanisms:
    """Тесты для retry механизмов"""

    @pytest.mark.asyncio
    async def test_eli_fetch_success_first_attempt(self, mock_session):
        """Тест успешного ELI fetch с первой попытки"""
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://eur-lex.europa.eu/sparql",
                content=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None
            assert "title" in result
            assert "content" in result

    @pytest.mark.asyncio
    async def test_eli_fetch_retry_on_failure(self, mock_session):
        """Тест retry для ELI fetch при неудаче"""
        with aioresponses() as m:
            # Первые 2 попытки неудачные, третья успешная
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=500,
                body="Server Error"
            )
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=503,
                body="Service Unavailable"
            )
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None
            assert "title" in result

    @pytest.mark.asyncio
    async def test_eli_fetch_max_retries_exceeded(self, mock_session):
        """Тест превышения максимального количества retry для ELI"""
        with aioresponses() as m:
            # Все попытки неудачные
            for _ in range(6):  # Больше чем max_attempts (5)
                m.add(
                    url="https://eur-lex.europa.eu/sparql",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_rss_fetch_success_first_attempt(self, mock_session):
        """Тест успешного RSS fetch с первой попытки"""
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            
            result = await fetch_rss(mock_session, "https://ec.europa.eu/info/feed/ai-act")
            
            assert result is not None
            assert len(result) > 0
            assert isinstance(result[0], tuple)
            assert len(result[0]) == 3  # title, link, description

    @pytest.mark.asyncio
    async def test_rss_fetch_retry_on_failure(self, mock_session):
        """Тест retry для RSS fetch при неудаче"""
        with aioresponses() as m:
            # Первые 2 попытки неудачные, третья успешная
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=500,
                body="Server Error"
            )
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=503,
                body="Service Unavailable"
            )
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=200,
                body=mock_rss_feed()
            )
            
            result = await fetch_rss(mock_session, "https://ec.europa.eu/info/feed/ai-act")
            
            assert result is not None
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rss_fetch_max_retries_exceeded(self, mock_session):
        """Тест превышения максимального количества retry для RSS"""
        with aioresponses() as m:
            # Все попытки неудачные
            for _ in range(6):  # Больше чем max_attempts (5)
                m.add(
                    url="https://ec.europa.eu/info/feed/ai-act",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            
            result = await fetch_rss(mock_session, "https://ec.europa.eu/info/feed/ai-act")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_retry_with_different_status_codes(self, mock_session):
        """Тест retry с разными кодами статуса"""
        test_data = create_retry_test_data()
        
        for test_case in test_data:
            with aioresponses() as m:
                # Настраиваем ответы в зависимости от тестового случая
                if test_case["should_retry"]:
                    # Добавляем несколько неудачных попыток
                    for _ in range(test_case["attempt"]):
                        m.add(
                            url="https://eur-lex.europa.eu/sparql",
                            method="GET",
                            status=test_case["status"],
                            body="Error"
                        )
                    
                    # Добавляем успешный ответ в конце
                    m.add(
                        url="https://eur-lex.europa.eu/sparql",
                        method="GET",
                        status=200,
                        body=json.dumps(mock_eli_response())
                    )
                else:
                    # Добавляем только неудачный ответ
                    m.add(
                        url="https://eur-lex.europa.eu/sparql",
                        method="GET",
                        status=test_case["status"],
                        body="Error"
                    )
                
                result = await fetch_latest_eli(mock_session, "32024R1689")
                
                if test_case["should_retry"] and test_case["status"] in [500, 503]:
                    assert result is not None
                elif test_case["status"] == 404:
                    assert result is None
                elif test_case["attempt"] >= 5:
                    assert result is None

    @pytest.mark.asyncio
    async def test_retry_with_network_errors(self, mock_session):
        """Тест retry с сетевыми ошибками"""
        with aioresponses() as m:
            # Сетевые ошибки
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                exception=asyncio.TimeoutError("Request timeout")
            )
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                exception=ConnectionError("Connection failed")
            )
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self, mock_session):
        """Тест exponential backoff в retry"""
        with aioresponses() as m:
            # Добавляем несколько неудачных попыток
            for _ in range(3):
                m.add(
                    url="https://eur-lex.europa.eu/sparql",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            start_time = datetime.now()
            result = await fetch_latest_eli(mock_session, "32024R1689")
            end_time = datetime.now()
            
            assert result is not None
            
            # Проверяем, что было время ожидания между попытками
            processing_time = (end_time - start_time).total_seconds()
            assert processing_time > 0.1  # Должно быть некоторое время ожидания

    @pytest.mark.asyncio
    async def test_retry_with_jitter(self, mock_session):
        """Тест jitter в retry механизме"""
        with aioresponses() as m:
            # Добавляем несколько неудачных попыток
            for _ in range(2):
                m.add(
                    url="https://eur-lex.europa.eu/sparql",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_different_urls(self, mock_session):
        """Тест retry с разными URL"""
        urls = [
            "https://eur-lex.europa.eu/sparql",
            "https://ec.europa.eu/info/feed/ai-act",
            "https://example.com/regulation"
        ]
        
        for url in urls:
            with aioresponses() as m:
                # Добавляем неудачную попытку
                m.add(
                    url=url,
                    method="GET",
                    status=500,
                    body="Server Error"
                )
                
                # Добавляем успешный ответ
                if "sparql" in url:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=json.dumps(mock_eli_response())
                    )
                elif "feed" in url:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=mock_rss_feed()
                    )
                else:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=mock_html_content()
                    )
                
                if "sparql" in url:
                    result = await fetch_latest_eli(mock_session, "32024R1689")
                    assert result is not None
                elif "feed" in url:
                    result = await fetch_rss(mock_session, url)
                    assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_invalid_json(self, mock_session):
        """Тест retry с невалидным JSON ответом"""
        with aioresponses() as m:
            # Добавляем ответ с невалидным JSON
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body="Invalid JSON"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_empty_response(self, mock_session):
        """Тест retry с пустым ответом"""
        with aioresponses() as m:
            # Добавляем пустой ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=""
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_redirects(self, mock_session):
        """Тест retry с редиректами"""
        with aioresponses() as m:
            # Добавляем редирект
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=301,
                body="Redirect"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_rate_limiting(self, mock_session):
        """Тест retry с rate limiting"""
        with aioresponses() as m:
            # Добавляем rate limit ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=429,
                body="Too Many Requests"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_authentication_errors(self, mock_session):
        """Тест retry с ошибками аутентификации"""
        with aioresponses() as m:
            # Добавляем ошибку аутентификации
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=401,
                body="Unauthorized"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_server_maintenance(self, mock_session):
        """Тест retry во время обслуживания сервера"""
        with aioresponses() as m:
            # Добавляем ответ о техническом обслуживании
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=503,
                body="Service Unavailable - Maintenance"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_retry_with_partial_failures(self, mock_session):
        """Тест retry с частичными неудачами"""
        with aioresponses() as m:
            # Добавляем частично неудачные ответы
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=206,
                body="Partial Content"
            )
            
            # Добавляем успешный ответ
            m.add(
                url="https://eur-lex.europa.eu/sparql",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            result = await fetch_latest_eli(mock_session, "32024R1689")
            
            assert result is not None


class TestRetryConfiguration:
    """Тесты конфигурации retry"""

    def test_retry_decorator_configuration(self):
        """Тест конфигурации retry декоратора"""
        # Проверяем, что декоратор правильно настроен
        from annex4parser.eli_client import fetch_latest_eli
        
        # Проверяем, что функция имеет retry декоратор
        assert hasattr(fetch_latest_eli, '__wrapped__')
        
        # Проверяем, что функция все еще callable
        assert callable(fetch_latest_eli)

    def test_retry_parameters(self):
        """Тест параметров retry"""
        from tenacity import Retrying
        
        # Создаем retry объект с теми же параметрами
        retry = Retrying(
            wait=wait_exponential_jitter(initial=5, max=300),
            stop=stop_after_attempt(5)
        )
        
        assert retry.stop.max_attempt_number == 5
        assert retry.wait.multiplier == 2  # exponential
        assert retry.wait.max == 300
        assert retry.wait.min == 5

    @pytest.mark.asyncio
    async def test_retry_with_custom_configuration(self, mock_session):
        """Тест retry с кастомной конфигурацией"""
        from tenacity import retry, stop_after_attempt, wait_fixed
        
        @retry(
            wait=wait_fixed(0.1),
            stop=stop_after_attempt(3)
        )
        async def custom_fetch(session, url):
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                return await response.text()
        
        with aioresponses() as m:
            # Добавляем неудачные попытки
            for _ in range(2):
                m.add(
                    url="https://example.com/test",
                    method="GET",
                    status=500,
                    body="Error"
                )
            
            # Добавляем успешный ответ
            m.add(
                url="https://example.com/test",
                method="GET",
                status=200,
                body="Success"
            )
            
            result = await custom_fetch(mock_session, "https://example.com/test")
            
            assert result == "Success"
