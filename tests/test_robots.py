import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from aioresponses import aioresponses
from urllib.parse import urlparse
from tests.helpers import mock_robots_txt, setup_aiohttp_mocks


class TestRobotsTxtHandling:
    """Тесты для обработки robots.txt"""

    @pytest.mark.asyncio
    async def test_robots_txt_allowed(self, mock_session):
        """Тест разрешенного доступа согласно robots.txt"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL
            setup_aiohttp_mocks(
                m, f"https://{domain}/test",
                content="Test content"
            )
            
            # Проверяем, что robots.txt разрешает доступ
            from annex4parser.robots_checker import check_robots_allowed
            
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_disallowed(self, mock_session):
        """Тест запрещенного доступа согласно robots.txt"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nDisallow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Проверяем, что robots.txt запрещает доступ
            from annex4parser.robots_checker import check_robots_allowed
            
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is False

    @pytest.mark.asyncio
    async def test_robots_txt_partial_disallow(self, mock_session):
        """Тест частичного запрета в robots.txt"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /\nDisallow: /private/"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # Проверяем разрешенный путь
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/public")
            assert is_allowed is True
            
            # Проверяем запрещенный путь
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/private")
            assert is_allowed is False

    @pytest.mark.asyncio
    async def test_robots_txt_not_found(self, mock_session):
        """Тест отсутствующего robots.txt"""
        domain = "example.com"
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock 404 для robots.txt
            m.add(
                url=robots_url,
                method="GET",
                status=404,
                body="Not Found"
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # При отсутствии robots.txt доступ должен быть разрешен
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_server_error(self, mock_session):
        """Тест ошибки сервера при получении robots.txt"""
        domain = "example.com"
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock 500 для robots.txt
            m.add(
                url=robots_url,
                method="GET",
                status=500,
                body="Server Error"
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # При ошибке сервера доступ должен быть разрешен (по умолчанию)
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_timeout(self, mock_session):
        """Тест таймаута при получении robots.txt"""
        domain = "example.com"
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock таймаут для robots.txt
            m.add(
                url=robots_url,
                method="GET",
                exception=asyncio.TimeoutError("Request timeout")
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # При таймауте доступ должен быть разрешен (по умолчанию)
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_specific_user_agent(self, mock_session):
        """Тест robots.txt с конкретным User-Agent"""
        domain = "example.com"
        robots_content = """User-agent: Annex4ComplianceBot
Disallow: /

User-agent: *
Allow: /"""
        
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # Проверяем с нашим User-Agent
            is_allowed = await check_robots_allowed(
                mock_session, 
                f"https://{domain}/test",
                user_agent="Annex4ComplianceBot"
            )
            
            assert is_allowed is False
            
            # Проверяем с другим User-Agent
            is_allowed = await check_robots_allowed(
                mock_session, 
                f"https://{domain}/test",
                user_agent="OtherBot"
            )
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_crawl_delay(self, mock_session):
        """Тест crawl-delay в robots.txt"""
        domain = "example.com"
        robots_content = """User-agent: *
Crawl-delay: 10
Allow: /"""
        
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            from annex4parser.robots_checker import get_crawl_delay
            
            delay = await get_crawl_delay(mock_session, f"https://{domain}/test")
            
            assert delay == 10

    @pytest.mark.asyncio
    async def test_robots_txt_no_crawl_delay(self, mock_session):
        """Тест отсутствия crawl-delay в robots.txt"""
        domain = "example.com"
        robots_content = """User-agent: *
Allow: /"""
        
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            from annex4parser.robots_checker import get_crawl_delay
            
            delay = await get_crawl_delay(mock_session, f"https://{domain}/test")
            
            assert delay == 0  # По умолчанию

    @pytest.mark.asyncio
    async def test_robots_txt_malformed(self, mock_session):
        """Тест некорректного robots.txt"""
        domain = "example.com"
        robots_content = """Invalid robots.txt content
No proper format"""
        
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # При некорректном robots.txt доступ должен быть разрешен
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_empty(self, mock_session):
        """Тест пустого robots.txt"""
        domain = "example.com"
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock пустой robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=""
            )
            
            from annex4parser.robots_checker import check_robots_allowed
            
            # При пустом robots.txt доступ должен быть разрешен
            is_allowed = await check_robots_allowed(mock_session, f"https://{domain}/test")
            
            assert is_allowed is True


class TestUserAgentHandling:
    """Тесты для обработки User-Agent"""

    def test_user_agent_construction(self):
        """Тест конструирования User-Agent"""
        from annex4parser.user_agent import get_user_agent
        
        user_agent = get_user_agent()
        
        assert "Annex4ComplianceBot" in user_agent
        assert "annex4parser" in user_agent.lower()
        assert "http" in user_agent.lower()

    def test_user_agent_with_contact(self):
        """Тест User-Agent с контактной информацией"""
        from annex4parser.user_agent import get_user_agent
        
        user_agent = get_user_agent(contact_url="https://example.com/contact")
        
        assert "Annex4ComplianceBot" in user_agent
        assert "example.com" in user_agent

    def test_user_agent_with_version(self):
        """Тест User-Agent с версией"""
        from annex4parser.user_agent import get_user_agent
        
        user_agent = get_user_agent(version="2.0")
        
        assert "Annex4ComplianceBot" in user_agent
        assert "2.0" in user_agent

    def test_user_agent_default_values(self):
        """Тест значений по умолчанию для User-Agent"""
        from annex4parser.user_agent import get_user_agent
        
        user_agent = get_user_agent()
        
        # Проверяем, что содержит основные компоненты
        assert "Annex4ComplianceBot" in user_agent
        assert "annex4parser" in user_agent.lower()


class TestEthicalScraping:
    """Тесты для этичного скрапинга"""

    @pytest.mark.asyncio
    async def test_respect_robots_txt_in_fetch(self, mock_session):
        """Тест уважения robots.txt при fetch"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nDisallow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL (не должен быть вызван)
            m.add(
                url=f"https://{domain}/test",
                method="GET",
                status=200,
                body="Test content"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            
            # Попытка fetch должна быть заблокирована
            result = await ethical_fetch(mock_session, f"https://{domain}/test")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_respect_crawl_delay(self, mock_session):
        """Тест уважения crawl-delay"""
        domain = "example.com"
        robots_content = """User-agent: *
Crawl-delay: 1
Allow: /"""
        
        robots_url = f"https://{domain}/robots.txt"
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL
            setup_aiohttp_mocks(
                m, f"https://{domain}/test",
                content="Test content"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            import time
            
            start_time = time.time()
            result = await ethical_fetch(mock_session, f"https://{domain}/test")
            end_time = time.time()
            
            assert result is not None
            # Проверяем, что было время ожидания
            assert (end_time - start_time) >= 0.5  # Минимум 0.5 секунды

    @pytest.mark.asyncio
    async def test_ethical_fetch_with_user_agent(self, mock_session):
        """Тест ethical fetch с правильным User-Agent"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL
            setup_aiohttp_mocks(
                m, f"https://{domain}/test",
                content="Test content"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            
            result = await ethical_fetch(mock_session, f"https://{domain}/test")
            
            assert result is not None
            assert "Test content" in result

    @pytest.mark.asyncio
    async def test_ethical_fetch_rate_limiting(self, mock_session):
        """Тест rate limiting в ethical fetch"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL
            setup_aiohttp_mocks(
                m, f"https://{domain}/test",
                content="Test content"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            import time
            
            # Делаем несколько запросов подряд
            start_time = time.time()
            results = []
            for _ in range(3):
                result = await ethical_fetch(mock_session, f"https://{domain}/test")
                results.append(result)
            end_time = time.time()
            
            # Все запросы должны быть успешными
            assert all(r is not None for r in results)
            
            # Должно быть время между запросами
            assert (end_time - start_time) >= 0.5

    @pytest.mark.asyncio
    async def test_ethical_fetch_error_handling(self, mock_session):
        """Тест обработки ошибок в ethical fetch"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock ошибки для основного URL
            m.add(
                url=f"https://{domain}/test",
                method="GET",
                status=500,
                body="Server Error"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            
            result = await ethical_fetch(mock_session, f"https://{domain}/test")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_ethical_fetch_cache(self, mock_session):
        """Тест кэширования в ethical fetch"""
        domain = "example.com"
        robots_url, robots_content = mock_robots_txt(
            domain, "User-agent: *\nAllow: /"
        )
        
        with aioresponses() as m:
            # Mock robots.txt
            setup_aiohttp_mocks(
                m, robots_url,
                content=robots_content
            )
            
            # Mock основного URL
            setup_aiohttp_mocks(
                m, f"https://{domain}/test",
                content="Test content"
            )
            
            from annex4parser.ethical_fetcher import ethical_fetch
            
            # Первый запрос
            result1 = await ethical_fetch(mock_session, f"https://{domain}/test")
            
            # Второй запрос (должен использовать кэш)
            result2 = await ethical_fetch(mock_session, f"https://{domain}/test")
            
            assert result1 is not None
            assert result2 is not None
            assert result1 == result2


class TestRobotsParser:
    """Тесты для парсера robots.txt"""

    def test_parse_robots_txt_simple(self):
        """Тест парсинга простого robots.txt"""
        from annex4parser.robots_parser import parse_robots_txt
        
        content = """User-agent: *
Allow: /
Disallow: /private/"""
        
        rules = parse_robots_txt(content)
        
        assert "*" in rules
        assert rules["*"]["allow"] == ["/"]
        assert rules["*"]["disallow"] == ["/private/"]

    def test_parse_robots_txt_multiple_agents(self):
        """Тест парсинга robots.txt с несколькими агентами"""
        from annex4parser.robots_parser import parse_robots_txt
        
        content = """User-agent: Annex4ComplianceBot
Disallow: /

User-agent: *
Allow: /"""
        
        rules = parse_robots_txt(content)
        
        assert "Annex4ComplianceBot" in rules
        assert "*" in rules
        assert rules["Annex4ComplianceBot"]["disallow"] == ["/"]
        assert rules["*"]["allow"] == ["/"]

    def test_parse_robots_txt_with_crawl_delay(self):
        """Тест парсинга robots.txt с crawl-delay"""
        from annex4parser.robots_parser import parse_robots_txt
        
        content = """User-agent: *
Crawl-delay: 10
Allow: /"""
        
        rules = parse_robots_txt(content)
        
        assert "*" in rules
        assert rules["*"]["crawl_delay"] == 10

    def test_parse_robots_txt_empty(self):
        """Тест парсинга пустого robots.txt"""
        from annex4parser.robots_parser import parse_robots_txt
        
        rules = parse_robots_txt("")
        
        assert rules == {}

    def test_parse_robots_txt_malformed(self):
        """Тест парсинга некорректного robots.txt"""
        from annex4parser.robots_parser import parse_robots_txt
        
        content = """Invalid content
No proper format"""
        
        rules = parse_robots_txt(content)
        
        # Должен вернуть пустой словарь или обработать ошибку
        assert isinstance(rules, dict)


