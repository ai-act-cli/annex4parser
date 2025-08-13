# rss_listener.py
"""RSS-листенер для instant-mode мониторинга регуляторных обновлений.

Этот модуль предоставляет асинхронный RSS-клиент с поддержкой tenacity retry
и экспоненциальным back-off для надёжного мониторинга регуляторных источников.
"""

import asyncio
import hashlib
import logging
from typing import Dict, List, Optional, Tuple
import aiohttp
import feedparser
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

logger = logging.getLogger(__name__)

# User-Agent для этичного скрапинга
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "Annex4ComplianceBot/1.2 (+https://your-domain.example/contact)"
)


@retry(
    wait=wait_exponential_jitter(initial=5, max=300),
    stop=stop_after_attempt(5)
)
async def fetch_rss(
    session: aiohttp.ClientSession, 
    url: str
) -> List[Tuple[str, str, str]]:
    """Получить RSS-фид с retry логикой.
    
    Parameters
    ----------
    session : aiohttp.ClientSession
        HTTP сессия для запросов
    url : str
        URL RSS-фида
        
    Returns
    -------
    List[Tuple[str, str, str]]
        Список кортежей (link, hash, title) для каждого элемента фида
    """
    try:
        async with session.get(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            },
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            raw = await resp.text()
            
        # Парсим RSS с feedparser
        feed = feedparser.parse(raw)
        
        results = []
        for entry in feed.entries:
            link = entry.get("link", "")
            title = entry.get("title", "")
            # Создаём хеш на основе link + title для уникальности
            content_hash = hashlib.sha256(
                f"{link}:{title}".encode()
            ).hexdigest()
            
            results.append((link, content_hash, title))
            
        logger.info(f"Fetched {len(results)} entries from RSS feed: {url}")
        return results
        
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error fetching RSS feed {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching RSS feed {url}: {e}")
        raise


async def fetch_rss_feed(url: str) -> List[Tuple[str, str, str]]:
    """Удобная функция для получения RSS-фида."""
    async with aiohttp.ClientSession() as session:
        return await fetch_rss(session, url)


class RSSMonitor:
    """Монитор RSS-фидов с поддержкой отслеживания изменений."""
    
    def __init__(self):
        self.seen_hashes = set()
    
    async def check_for_updates(
        self, 
        url: str
    ) -> List[Tuple[str, str, str]]:
        """Проверить RSS-фид на новые элементы.
        
        Parameters
        ----------
        url : str
            URL RSS-фида
            
        Returns
        -------
        List[Tuple[str, str, str]]
            Список новых элементов (link, hash, title)
        """
        entries = await fetch_rss_feed(url)
        
        new_entries = []
        for link, content_hash, title in entries:
            if content_hash not in self.seen_hashes:
                new_entries.append((link, content_hash, title))
                self.seen_hashes.add(content_hash)
        
        if new_entries:
            logger.info(f"Found {len(new_entries)} new entries in RSS feed: {url}")
        else:
            logger.debug(f"No new entries in RSS feed: {url}")
            
        return new_entries

    def check_new_entries(self, entries: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """Вернуть только новые элементы (по хешу), обновляя seen_hashes."""
        new_entries = []
        for link, content_hash, title in entries:
            if content_hash not in self.seen_hashes:
                new_entries.append((link, content_hash, title))
                self.seen_hashes.add(content_hash)
        return new_entries


# Примеры популярных регуляторных RSS-фидов
REGULATORY_RSS_FEEDS = {
    "ep_plenary": "https://www.europarl.europa.eu/rss/doc/debates-plenary/en.xml",
    # Предопределённый фид EUR-Lex "All Parliament and Council legislation"
    "eurlex_latest_legislation": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162",
    "ec_press": "https://ec.europa.eu/commission/presscorner/rss/en.xml",
    "eiopa": "https://www.eiopa.europa.eu/rss/en.xml",
}


# Примеры использования
if __name__ == "__main__":
    async def test_rss():
        # Тестируем RSS-монитор
        monitor = RSSMonitor()

        # Проверяем EUR-Lex RSS (предопределённый фид)
        updates = await monitor.check_for_updates(REGULATORY_RSS_FEEDS["eurlex_latest_legislation"])
        
        for link, content_hash, title in updates:
            print(f"New: {title}")
            print(f"Link: {link}")
            print(f"Hash: {content_hash[:16]}...")
            print("-" * 50)
    
    asyncio.run(test_rss())


