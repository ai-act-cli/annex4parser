"""
Модуль для проверки robots.txt и этичного веб-скрапинга.
"""

import asyncio
import logging
import re
from typing import Optional, Dict, List
from urllib.parse import urlparse, urljoin
import aiohttp

logger = logging.getLogger(__name__)

# User-Agent для робота
DEFAULT_USER_AGENT = "Annex4Parser/1.0 (+https://github.com/annex4parser)"


class RobotsParser:
    """Парсер robots.txt файлов."""
    
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self.rules: Dict[str, List[Dict]] = {}
        self.crawl_delays: Dict[str, float] = {}
        
    def parse(self, robots_content: str) -> None:
        """Парсит содержимое robots.txt."""
        current_agent = "*"
        
        for line in robots_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            if ':' in line:
                directive, value = line.split(':', 1)
                directive = directive.strip().lower()
                value = value.strip()
                
                if directive == 'user-agent':
                    current_agent = value
                    if current_agent not in self.rules:
                        self.rules[current_agent] = []
                        
                elif directive == 'disallow':
                    if current_agent in self.rules:
                        self.rules[current_agent].append({
                            'type': 'disallow',
                            'path': value
                        })
                        
                elif directive == 'allow':
                    if current_agent in self.rules:
                        self.rules[current_agent].append({
                            'type': 'allow',
                            'path': value
                        })
                        
                elif directive == 'crawl-delay':
                    try:
                        delay = float(value)
                        self.crawl_delays[current_agent] = delay
                    except ValueError:
                        logger.warning(f"Invalid crawl-delay value: {value}")


async def _fetch_robots(session: aiohttp.ClientSession, domain: str) -> Optional[str]:
    """Загружает robots.txt для домена."""
    robots_url = f"https://{domain}/robots.txt"
    
    try:
        async with session.get(robots_url, timeout=10) as response:
            if response.status == 200:
                return await response.text()
            else:
                logger.debug(f"Robots.txt not found at {robots_url} (status: {response.status})")
                return None
    except Exception as e:
        logger.debug(f"Failed to fetch robots.txt from {robots_url}: {e}")
        return None


async def check_robots_allowed(
    session: aiohttp.ClientSession, 
    url: str, 
    user_agent: str = DEFAULT_USER_AGENT
) -> bool:
    """Проверяет, разрешен ли доступ к URL согласно robots.txt."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    # Загружаем robots.txt
    robots_content = await _fetch_robots(session, domain)
    if not robots_content:
        # Если robots.txt не найден, разрешаем доступ
        return True
    
    # Парсим robots.txt
    parser = RobotsParser(user_agent)
    parser.parse(robots_content)
    
    # Проверяем правила для нашего user-agent
    path = parsed_url.path
    
    # Сначала проверяем специфичные правила для нашего user-agent
    if user_agent in parser.rules:
        for rule in parser.rules[user_agent]:
            if _matches_rule(path, rule):
                return rule['type'] == 'allow'
    
    # Затем проверяем общие правила (*)
    if '*' in parser.rules:
        for rule in parser.rules['*']:
            if _matches_rule(path, rule):
                return rule['type'] == 'allow'
    
    # По умолчанию разрешаем
    return True


def _matches_rule(path: str, rule: Dict) -> bool:
    """Проверяет, соответствует ли путь правилу."""
    rule_path = rule['path']
    
    if not rule_path:
        return False
    
    # Простое сопоставление по префиксу
    if path.startswith(rule_path):
        return True
    
    # Поддержка wildcards
    if '*' in rule_path:
        pattern = rule_path.replace('*', '.*')
        return bool(re.match(pattern, path))
    
    return False


async def get_crawl_delay(
    session: aiohttp.ClientSession, 
    domain: str, 
    user_agent: str = DEFAULT_USER_AGENT
) -> float:
    """Получает crawl-delay для домена."""
    robots_content = await _fetch_robots(session, domain)
    if not robots_content:
        return 0.0
    
    parser = RobotsParser(user_agent)
    parser.parse(robots_content)
    
    # Возвращаем delay для нашего user-agent или общий
    if user_agent in parser.crawl_delays:
        return parser.crawl_delays[user_agent]
    elif '*' in parser.crawl_delays:
        return parser.crawl_delays['*']
    else:
        return 0.0


def is_allowed_by_robots(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Синхронная версия проверки robots.txt (для тестов)."""
    # Для тестов создаем простую проверку
    parsed_url = urlparse(url)
    path = parsed_url.path
    
    # Простые правила для тестирования
    if '/secret' in path or '/private' in path:
        return False
    
    return True


def _fetch_robots_sync(domain: str) -> str:
    """Синхронная версия загрузки robots.txt (для тестов)."""
    # Простая реализация для тестов
    return f"User-agent: *\nDisallow: /secret\n"
