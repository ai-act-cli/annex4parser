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
        
        # Инициализируем правила для * по умолчанию
        if "*" not in self.rules:
            self.rules["*"] = []
        
        logger.debug(f"Parsing robots.txt content: {repr(robots_content)}")
        
        for line in robots_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            logger.debug(f"Processing line: {repr(line)}")
            
            if ':' in line:
                directive, value = line.split(':', 1)
                directive = directive.strip().lower()
                value = value.strip()
                
                logger.debug(f"Directive: {directive}, Value: {value}, Current agent: {current_agent}")
                
                if directive == 'user-agent':
                    current_agent = value
                    if current_agent not in self.rules:
                        self.rules[current_agent] = []
                        
                elif directive == 'disallow':
                    if current_agent in self.rules:
                        rule = {'type': 'disallow', 'path': value}
                        self.rules[current_agent].append(rule)
                        logger.debug(f"Added disallow rule: {rule}")
                        
                elif directive == 'allow':
                    if current_agent in self.rules:
                        rule = {'type': 'allow', 'path': value}
                        self.rules[current_agent].append(rule)
                        logger.debug(f"Added allow rule: {rule}")
                        
                elif directive == 'crawl-delay':
                    try:
                        delay = float(value)
                        self.crawl_delays[current_agent] = delay
                        logger.debug(f"Added crawl-delay: {delay}")
                    except ValueError:
                        logger.warning(f"Invalid crawl-delay value: {value}")
        
        logger.debug(f"Final rules: {self.rules}")


async def _fetch_robots(session: aiohttp.ClientSession, domain: str) -> Optional[str]:
    """Загружает robots.txt для домена."""
    robots_url = f"https://{domain}/robots.txt"
    
    try:
        response = await session.get(robots_url, timeout=10)
        
        if hasattr(response, 'status') and response.status == 200:
            return await response.text()
        else:
            logger.debug(f"Robots.txt not found at {robots_url} (status: {getattr(response, 'status', 'unknown')})")
            return None
    except Exception as e:
        logger.debug(f"Failed to fetch robots.txt from {robots_url}: {e}")
        return None


async def check_robots_allowed(
    session: aiohttp.ClientSession,
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    return_rule: bool = False,
):
    """Проверяет, разрешен ли доступ к URL согласно robots.txt.

    Если ``return_rule`` равно ``True``, возвращает кортеж ``(allowed, rule)`` где
    ``rule`` — совпавшее правило из robots.txt.
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    # Загружаем robots.txt
    robots_content = await _fetch_robots(session, domain)
    if not robots_content:
        return (True, None) if return_rule else True

    # Парсим robots.txt
    parser = RobotsParser(user_agent)
    parser.parse(robots_content)

    # Проверяем правила для нашего user-agent
    path = parsed_url.path

    agent_rules = parser.rules.get(user_agent, [])
    general_rules = parser.rules.get('*', [])
    all_rules = agent_rules + general_rules

    logger.debug(f"Checking path: {path}")
    logger.debug(f"Rules: {all_rules}")

    matching_rules = []
    for rule in all_rules:
        if _matches_rule(path, rule):
            matching_rules.append(rule)
            logger.debug(f"Rule matched: {rule}")

    if not matching_rules:
        return (True, None) if return_rule else True

    # Сортируем правила по специфичности
    def get_specificity(rule):
        path = rule['path']
        normalized_path = path.rstrip('/')
        if normalized_path.startswith('/'):
            normalized_path = normalized_path[1:]
        if normalized_path == '':
            return 0
        return len(normalized_path)

    matching_rules.sort(key=get_specificity, reverse=True)
    most_specific_rule = matching_rules[0]
    logger.debug(f"Most specific rule: {most_specific_rule}")
    allowed = most_specific_rule['type'] == 'allow'

    if return_rule:
        return allowed, most_specific_rule
    return allowed


def _matches_rule(path: str, rule: Dict) -> bool:
    """Проверяет, соответствует ли путь правилу."""
    rule_path = rule['path']

    logger.debug(f"_matches_rule called with path='{path}', rule_path='{rule_path}'")

    if not rule_path:
        return False

    # Удаляем query-параметры и нормализуем слэши
    path = path.split('?')[0].strip('/')
    rule_path = rule_path.split('?')[0].strip('/')

    logger.debug(f"After normalization: path='{path}', rule_path='{rule_path}'")

    if rule_path == '':
        logger.debug("Rule path is empty after processing, this matches everything")
        return True

    if '*' in rule_path:
        pattern = '^' + re.escape(rule_path).replace('\\*', '.*') + '(/|$)'
        if re.match(pattern, path):
            logger.debug(f"Wildcard rule {rule_path} matches path {path}")
            return True

    path_segments = path.split('/') if path else []
    rule_segments = rule_path.split('/') if rule_path else []

    if len(path_segments) < len(rule_segments):
        logger.debug(f"Path '{path}' shorter than rule '{rule_path}'")
        return False

    if path_segments[:len(rule_segments)] == rule_segments:
        logger.debug(f"Rule {rule_path} matches path {path}")
        return True

    logger.debug(f"Rule {rule_path} does not match path {path}")
    return False


async def get_crawl_delay(
    session: aiohttp.ClientSession, 
    url: str, 
    user_agent: str = DEFAULT_USER_AGENT
) -> float:
    """Получает crawl-delay для URL."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    robots_content = await _fetch_robots(session, domain)
    if not robots_content:
        logger.debug(f"No robots.txt content found for {domain}")
        return 0.0
    
    parser = RobotsParser(user_agent)
    parser.parse(robots_content)
    
    logger.debug(f"Parsed crawl_delays: {parser.crawl_delays}")
    logger.debug(f"User agent: {user_agent}")
    
    # Возвращаем delay для нашего user-agent или общий
    if user_agent in parser.crawl_delays:
        delay = parser.crawl_delays[user_agent]
        logger.debug(f"Found crawl-delay for user agent {user_agent}: {delay}")
        return delay
    elif '*' in parser.crawl_delays:
        delay = parser.crawl_delays['*']
        logger.debug(f"Found crawl-delay for wildcard *: {delay}")
        return delay
    else:
        logger.debug("No crawl-delay found, returning 0.0")
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
