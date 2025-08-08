"""
Модуль для этичного получения данных с учетом robots.txt
"""

import asyncio
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from .robots_checker import check_robots_allowed, get_crawl_delay
from .user_agent import get_user_agent


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
        is_allowed = await check_robots_allowed(self.session, url, self.user_agent)
        if not is_allowed:
            return None
        
        # Получаем crawl-delay
        delay = await get_crawl_delay(self.session, url, self.user_agent)
        
        # Соблюдаем crawl-delay
        await self._respect_crawl_delay(url, delay)
        
        try:
            # Делаем запрос
            headers = {'User-Agent': self.user_agent}
            response = await self.session.get(url, headers=headers)
            
            if hasattr(response, 'status') and response.status == 200:
                content = await response.text()
                
                # Кэшируем результат
                if use_cache:
                    self.cache[url] = content
                
                return content
            else:
                return None
        except Exception:
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
