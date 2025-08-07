#!/usr/bin/env python3
"""
Pytest configuration and fixtures
"""

import pytest
import asyncio
import pathlib
from unittest.mock import Mock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
from freezegun import freeze_time
import aiohttp
from annex4parser.models import Base, Source, RegulationSourceLog
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.eli_client import fetch_latest_eli
from annex4parser.rss_listener import fetch_rss, RSSMonitor
from annex4parser.legal_diff import LegalDiffAnalyzer
from annex4parser.alerts.webhook import AlertEmitter


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для async тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db():
    """Создает in-memory SQLite базу для тестов"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    engine.dispose()


@pytest.fixture
def sample_sources():
    """Тестовые источники данных"""
    return [
        {
            "id": "test_eli",
            "url": "https://eur-lex.europa.eu/eli/reg/2024/1689",
            "type": "eli_sparql",
            "freq": "6h",
            "celex_id": "32024R1689",
            "description": "Test EU AI Act"
        },
        {
            "id": "test_rss",
            "url": "https://ec.europa.eu/info/feed/ai-act",
            "type": "rss",
            "freq": "1h",
            "description": "Test RSS feed"
        },
        {
            "id": "test_html",
            "url": "https://example.com/regulation",
            "type": "html",
            "freq": "24h",
            "description": "Test HTML source"
        }
    ]


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer"""
    producer = Mock()
    producer.send = Mock()
    producer.flush = Mock()
    return producer


@pytest.fixture
def sample_eli_response():
    """Тестовый ответ ELI SPARQL"""
    return {
        "results": {
            "bindings": [
                {
                    "title": {"value": "EU AI Act"},
                    "content": {"value": "Article 1. Scope. This Regulation applies to..."},
                    "date": {"value": "2024-01-15"},
                    "celex": {"value": "32024R1689"}
                }
            ]
        }
    }


@pytest.fixture
def sample_rss_feed():
    """Тестовый RSS feed"""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>EU AI Act Updates</title>
            <item>
                <title>New AI Act Guidelines</title>
                <link>https://example.com/guidelines</link>
                <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
                <description>Updated guidelines for AI Act implementation</description>
            </item>
        </channel>
    </rss>"""


@pytest.fixture
def sample_html_content():
    """Тестовый HTML контент"""
    return """
    <html>
        <body>
            <h1>EU AI Act</h1>
            <p>Article 1. Scope. This Regulation applies to...</p>
            <p>Article 2. Definitions. For the purposes of this Regulation...</p>
        </body>
    </html>
    """


@pytest.fixture
def legal_diff_analyzer():
    """Экземпляр LegalDiffAnalyzer"""
    return LegalDiffAnalyzer()


@pytest.fixture
def alert_emitter(mock_kafka_producer):
    """Экземпляр AlertEmitter с mock Kafka"""
    emitter = AlertEmitter(
        webhook_url="https://example.com/webhook",
        kafka_bootstrap_servers="localhost:9092"
    )
    emitter.producer = mock_kafka_producer
    return emitter


@pytest.fixture
def rss_monitor():
    """Экземпляр RSSMonitor"""
    return RSSMonitor()


@pytest.fixture
@freeze_time("2024-01-15 10:00:00")
def frozen_time():
    """Фиксированное время для тестов"""
    return datetime(2024, 1, 15, 10, 0, 0)


# ---- sample payloads -------------------------------------------------
@pytest.fixture
def eli_rdf_v1():
    """Тестовый ELI RDF v1"""
    return pathlib.Path("tests/data/eli_v1.ttl").read_text()


@pytest.fixture
def eli_rdf_v2():
    """Тестовый ELI RDF v2 с major изменениями"""
    return pathlib.Path("tests/data/eli_v2_major.ttl").read_text()


@pytest.fixture
def rss_xml_minor():
    """Тестовый RSS XML с minor изменениями"""
    return pathlib.Path("tests/data/rss_minor.xml").read_text()


@pytest.fixture
def test_config_path():
    """Создает временный конфигурационный файл для тестов"""
    import tempfile
    import yaml
    from pathlib import Path
    
    test_config = {
        'sources': [
            {
                'id': 'celex',
                'url': 'https://publications.europa.eu/webapi/rdf/sparql',
                'type': 'eli_sparql',
                'freq': '6h',
                'extra': {'celex_id': '32024R1689'}
            },
            {
                'id': 'test_eli',
                'url': 'https://example.com/eli',
                'type': 'eli_sparql',
                'freq': '6h'
            },
            {
                'id': 'test_rss',
                'url': 'https://example.com/rss',
                'type': 'rss',
                'freq': '1h'
            },
            {
                'id': 'test_html',
                'url': 'https://example.com/html',
                'type': 'html',
                'freq': '24h'
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(test_config, f)
        config_path = Path(f.name)
    
    yield config_path
    
    # Удаляем временный файл после теста
    config_path.unlink(missing_ok=True)


@pytest.fixture
def real_config_path():
    """Использует существующий YAML файл из проекта"""
    from pathlib import Path
    config_path = Path(__file__).parent.parent / "annex4parser" / "sources.yaml"
    return config_path


@pytest.fixture
def test_regulation(test_db):
    """Создает тестовое регулирование с правилами"""
    from annex4parser.models import Regulation, Rule
    
    # Создаем регулирование
    regulation = Regulation(
        name="EU AI Act",
        version="1.0"
    )
    test_db.add(regulation)
    test_db.flush()
    
    # Создаем правила
    rules = [
        Rule(
            regulation_id=regulation.id,
            section_code="Article9.2",
            content="Risk management system requirements for high-risk AI systems",
            risk_level="critical"
        ),
        Rule(
            regulation_id=regulation.id,
            section_code="Article10.1",
            content="Data governance and quality requirements for training datasets",
            risk_level="high"
        ),
        Rule(
            regulation_id=regulation.id,
            section_code="Article15.3",
            content="Technical documentation requirements for AI systems",
            risk_level="medium"
        ),
        Rule(
            regulation_id=regulation.id,
            section_code="Article15.4",
            content="Record keeping and logging requirements for AI systems",
            risk_level="medium"
        ),
        Rule(
            regulation_id=regulation.id,
            section_code="Article16.1",
            content="Accuracy and cybersecurity requirements for AI systems",
            risk_level="high"
        ),
        Rule(
            regulation_id=regulation.id,
            section_code="Article17.1",
            content="Human oversight requirements for AI systems",
            risk_level="critical"
        )
    ]
    
    for rule in rules:
        test_db.add(rule)
    
    test_db.commit()
    return regulation
