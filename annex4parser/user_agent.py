"""
Модуль для работы с User-Agent строками
"""

import platform
import sys
from typing import Optional


def get_user_agent(
    contact_url: Optional[str] = None,
    version: Optional[str] = None
) -> str:
    """
    Создает User-Agent строку для бота
    
    Args:
        contact_url: URL для контактной информации
        version: Версия бота
        
    Returns:
        User-Agent строка
    """
    bot_name = "Annex4ComplianceBot"
    
    # Основная информация о боте
    user_agent_parts = [bot_name]
    
    # Добавляем версию
    if version:
        user_agent_parts.append(f"v{version}")
    else:
        user_agent_parts.append("v1.0")
    
    # Добавляем информацию о библиотеке
    user_agent_parts.append("annex4parser")
    
    # Добавляем информацию о системе
    user_agent_parts.append(f"({platform.system()}; {platform.machine()})")
    
    # Добавляем информацию о Python
    user_agent_parts.append(f"Python/{sys.version_info.major}.{sys.version_info.minor}")
    
    # Добавляем контактную информацию
    if contact_url:
        user_agent_parts.append(f"+{contact_url}")
    else:
        user_agent_parts.append("+https://github.com/annex4parser")
    
    return " ".join(user_agent_parts)


def get_default_user_agent() -> str:
    """
    Возвращает User-Agent по умолчанию
    
    Returns:
        User-Agent строка по умолчанию
    """
    return get_user_agent()
