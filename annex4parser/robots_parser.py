"""
Модуль для парсинга robots.txt файлов
"""

import re
from typing import Dict, List, Any


def parse_robots_txt(content: str) -> Dict[str, Dict[str, Any]]:
    """
    Парсит содержимое robots.txt файла
    
    Args:
        content: Содержимое robots.txt файла
        
    Returns:
        Словарь с правилами для каждого User-Agent
    """
    if not content or not content.strip():
        return {}
    
    rules = {}
    current_agent = None
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Пропускаем пустые строки и комментарии
        if not line or line.startswith('#'):
            continue
        
        # Ищем User-agent
        if line.lower().startswith('user-agent:'):
            agent = line.split(':', 1)[1].strip()
            if agent:
                current_agent = agent
                if current_agent not in rules:
                    rules[current_agent] = {
                        'allow': [],
                        'disallow': [],
                        'crawl_delay': None
                    }
        
        # Ищем Allow
        elif line.lower().startswith('allow:') and current_agent:
            path = line.split(':', 1)[1].strip()
            if path:
                rules[current_agent]['allow'].append(path)
        
        # Ищем Disallow
        elif line.lower().startswith('disallow:') and current_agent:
            path = line.split(':', 1)[1].strip()
            if path:
                rules[current_agent]['disallow'].append(path)
        
        # Ищем Crawl-delay
        elif line.lower().startswith('crawl-delay:') and current_agent:
            try:
                delay = float(line.split(':', 1)[1].strip())
                rules[current_agent]['crawl_delay'] = delay
            except (ValueError, IndexError):
                pass
    
    return rules


def is_path_allowed(path: str, rules: Dict[str, Any], user_agent: str = "*") -> bool:
    """
    Проверяет, разрешен ли доступ к пути согласно правилам
    
    Args:
        path: Путь для проверки
        rules: Правила robots.txt
        user_agent: User-Agent для проверки
        
    Returns:
        True если доступ разрешен, False если запрещен
    """
    # Сначала проверяем конкретный User-Agent
    if user_agent in rules:
        agent_rules = rules[user_agent]
    elif "*" in rules:
        agent_rules = rules["*"]
    else:
        return True  # Если нет правил, разрешаем доступ
    
    # Проверяем disallow правила
    for disallow_path in agent_rules.get('disallow', []):
        if _path_matches(path, disallow_path):
            return False
    
    # Проверяем allow правила
    for allow_path in agent_rules.get('allow', []):
        if _path_matches(path, allow_path):
            return True
    
    # Если есть disallow правила, но нет allow, то запрещаем
    if agent_rules.get('disallow') and not agent_rules.get('allow'):
        return False
    
    return True


def get_crawl_delay(rules: Dict[str, Any], user_agent: str = "*") -> float:
    """
    Получает crawl-delay для User-Agent
    
    Args:
        rules: Правила robots.txt
        user_agent: User-Agent
        
    Returns:
        Crawl-delay в секундах, 0 если не указан
    """
    if user_agent in rules:
        return rules[user_agent].get('crawl_delay', 0)
    elif "*" in rules:
        return rules["*"].get('crawl_delay', 0)
    return 0


def _path_matches(path: str, pattern: str) -> bool:
    """
    Проверяет, соответствует ли путь паттерну
    
    Args:
        path: Путь для проверки
        pattern: Паттерн из robots.txt
        
    Returns:
        True если путь соответствует паттерну
    """
    if not pattern:
        return False
    
    # Убираем начальный слеш для сравнения
    path = path.lstrip('/')
    pattern = pattern.lstrip('/')
    
    # Если паттерн пустой, разрешаем все
    if not pattern:
        return True
    
    # Простое сравнение (можно улучшить с помощью regex)
    return path.startswith(pattern)
