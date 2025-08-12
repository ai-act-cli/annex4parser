"""
Модуль для этичного получения данных с учетом robots.txt
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin
from urllib import robotparser

import aiohttp

from .robots_checker import get_crawl_delay
from .user_agents import get_user_agent

logger = logging.getLogger(__name__)


async def allowed_by_robots(session, url: str, user_agent: str) -> bool:
    """Check robots.txt for the given URL using urllib.robotparser."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urljoin(base, "/robots.txt")
    rp = robotparser.RobotFileParser()
    try:
        async with session.get(robots_url) as resp:
            if resp.status != 200:
                return True
            content = await resp.text()
        rp.parse(content.splitlines())
    except Exception:
        return True
    return rp.can_fetch(user_agent, url)


class EthicalFetcher:
    """Класс для этичного получения данных"""
    
    def __init__(self, session, user_agent: Optional[str] = None):
        """
        Инициализация fetcher
        
        Args:
            session: aiohttp сессия
            user_agent: User-Agent строка
        """
        self.session = session
        self.user_agent = user_agent or get_user_agent()
        self.last_request_time: Dict[str, float] = {}
        self.cache: Dict[str, Any] = {}
    
    async def fetch(self, url: str, use_cache: bool = True) -> Optional[str]:
        """
        Этично получает данные по URL
        
        Args:
            url: URL для получения
            use_cache: Использовать ли кэш
            
        Returns:
            Содержимое страницы или None при ошибке
        """
        # Проверяем кэш
        if use_cache and url in self.cache:
            return self.cache[url]
        
        # Проверяем robots.txt
        allowed = await allowed_by_robots(self.session, url, self.user_agent)
        if not allowed:
            parsed = urlparse(url)
            logger.warning(
                f"Robots disallow: domain={parsed.netloc}, path={parsed.path}"
            )
            return None
        
        # Получаем crawl-delay
        delay = await get_crawl_delay(self.session, url, self.user_agent)
        
        # Соблюдаем crawl-delay
        await self._respect_crawl_delay(url, delay)
        
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en',
            }
            response = await self.session.get(url, headers=headers)
            response.raise_for_status()
            content = await response.text()

            if use_cache:
                self.cache[url] = content

            return content
        except aiohttp.ClientResponseError as e:
            logger.error(
                "HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            raise
        except Exception:
            logger.exception("Failed to fetch %s", url)
            return None
    
    async def _respect_crawl_delay(self, url: str, delay: float):
        """
        Соблюдает crawl-delay для домена
        
        Args:
            url: URL
            delay: Задержка в секундах
        """
        domain = urlparse(url).netloc
        current_time = time.time()
        
        if domain in self.last_request_time:
            time_since_last = current_time - self.last_request_time[domain]
            if time_since_last < delay:
                sleep_time = delay - time_since_last
                await asyncio.sleep(sleep_time)
        
        self.last_request_time[domain] = time.time()


# Глобальный кэш для экземпляров EthicalFetcher
_fetcher_cache: Dict[str, EthicalFetcher] = {}

async def ethical_fetch(session, url: str, user_agent: Optional[str] = None) -> Optional[str]:
    """
    Удобная функция для этичного получения данных
    
    Args:
        session: aiohttp сессия
        url: URL для получения
        user_agent: User-Agent строка
        
    Returns:
        Содержимое страницы или None при ошибке
    """
    # Создаем ключ для кэша на основе session и user_agent
    cache_key = f"{id(session)}_{user_agent or 'default'}"
    
    if cache_key not in _fetcher_cache:
        _fetcher_cache[cache_key] = EthicalFetcher(session, user_agent)
    
    return await _fetcher_cache[cache_key].fetch(url)
