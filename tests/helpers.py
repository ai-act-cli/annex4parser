import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import Mock, AsyncMock
import aiohttp
from aioresponses import aioresponses
from annex4parser.models import Source, RegulationSourceLog


def create_test_source(
    source_id: str,
    source_type: str = "eli_sparql",
    url: str = "https://example.com/test",
    freq: str = "6h",
    active: bool = True
) -> Source:
    """Создает тестовый источник данных"""
    return Source(
        id=source_id,
        url=url,
        type=source_type,
        freq=freq,
        active=active,
        last_fetched=datetime.now() - timedelta(hours=1),
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


def create_test_log_entry(
    source_id: str,
    status: str = "success",
    content_hash: str = "test_hash_123",
    response_time: float = 1.5,
    error_message: Optional[str] = None
) -> RegulationSourceLog:
    """Создает тестовую запись лога"""
    return RegulationSourceLog(
        source_id=source_id,
        status=status,
        fetched_at=datetime.now(),
        content_hash=content_hash,
        response_time=response_time,
        error_message=error_message,
        bytes_downloaded=1024
    )


def mock_eli_response(title: str = "Test Regulation", content: str = "Test content"):
    """Создает mock ответ ELI SPARQL"""
    return {
        "results": {
            "bindings": [
                {
                    "title": {"value": title},
                    "content": {"value": content},
                    "date": {"value": "2024-01-15"},
                    "celex": {"value": "32024R1689"}
                }
            ]
        }
    }


def mock_rss_feed(title: str = "Test Update", link: str = "https://example.com/update"):
    """Создает mock RSS feed"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>{title}</title>
                <link>{link}</link>
                <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
                <description>Test description</description>
            </item>
        </channel>
    </rss>"""


def mock_html_content(title: str = "Test Regulation", content: str = "Test content"):
    """Создает mock HTML контент"""
    return f"""
    <html>
        <head><title>{title}</title></head>
        <body>
            <h1>{title}</h1>
            <p>{content}</p>
        </body>
    </html>
    """


def calculate_content_hash(content: str) -> str:
    """Вычисляет хеш контента"""
    return hashlib.sha256(content.encode()).hexdigest()


def create_mock_response(
    status: int = 200,
    content: str = "test content",
    headers: Optional[Dict] = None
) -> Mock:
    """Создает mock HTTP ответ"""
    response = Mock()
    response.status = status
    response.headers = headers or {}
    response.text = AsyncMock(return_value=content)
    response.read = AsyncMock(return_value=content.encode())
    return response


def setup_aiohttp_mocks(
    m: aioresponses,
    url: str,
    method: str = "GET",
    status: int = 200,
    content: str = "test content",
    headers: Optional[Dict] = None
):
    """Настраивает mock для aiohttp запросов"""
    m.add(
        url=url,
        method=method,
        status=status,
        body=content,
        headers=headers or {}
    )


def create_test_regulation_data(
    name: str = "Test Regulation",
    version: str = "1.0",
    rules: Optional[List[Dict]] = None
) -> Dict:
    """Создает тестовые данные регуляции"""
    if rules is None:
        rules = [
            {
                "section_code": "Article1.1",
                "title": "Scope",
                "content": "This Regulation applies to..."
            },
            {
                "section_code": "Article2.1", 
                "title": "Definitions",
                "content": "For the purposes of this Regulation..."
            }
        ]
    
    return {
        "name": name,
        "version": version,
        "source_url": "https://example.com/regulation",
        "status": "active",
        "rules": rules
    }


def create_test_alert_payload(
    rule_id: str = "test_rule_123",
    severity: str = "high",
    regulation_name: str = "Test Regulation",
    section_code: str = "Article1.1",
    change_type: str = "update"
) -> Dict:
    """Создает тестовый payload для алерта"""
    return {
        "rule_id": rule_id,
        "severity": severity,
        "regulation_name": regulation_name,
        "section_code": section_code,
        "change_type": change_type,
        "timestamp": datetime.now().isoformat(),
        "source": "annex4parser"
    }


def assert_kafka_message_sent(producer_mock, topic: str, payload: Dict):
    """Проверяет, что сообщение было отправлено в Kafka"""
    producer_mock.send.assert_called_with(topic, payload)


def assert_webhook_called(session_mock, url: str, payload: Dict):
    """Проверяет, что webhook был вызван"""
    session_mock.post.assert_called_with(
        url,
        json=payload,
        headers={"Content-Type": "application/json"}
    )


def create_test_diff_data(
    old_text: str = "Old content",
    new_text: str = "New content",
    section_code: str = "Article1.1"
) -> Dict:
    """Создает тестовые данные для diff анализа"""
    return {
        "old_text": old_text,
        "new_text": new_text,
        "section_code": section_code
    }


def mock_robots_txt(domain: str = "example.com", content: str = "User-agent: *\nAllow: /"):
    """Создает mock robots.txt"""
    return f"https://{domain}/robots.txt", content


def create_retry_test_data() -> List[Dict]:
    """Создает данные для тестирования retry механизмов"""
    return [
        {"attempt": 1, "status": 500, "should_retry": True},
        {"attempt": 2, "status": 503, "should_retry": True},
        {"attempt": 3, "status": 200, "should_retry": False},
        {"attempt": 4, "status": 404, "should_retry": False},
        {"attempt": 5, "status": 500, "should_retry": False}  # max attempts reached
    ]


