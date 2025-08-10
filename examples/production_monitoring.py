# production_monitoring.py
"""Пример production-grade мониторинга регуляторов.

Этот пример демонстрирует использование всех новых компонентов:
- Мультисорс-фетчинг с ELI SPARQL и RSS
- Асинхронная обработка
- Event-driven алерты
- Юридически осмысленный diff-анализ
"""

import asyncio
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from annex4parser.models import Base
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2, update_all_regulations
from annex4parser.alerts import AlertEmitter, get_alert_emitter
from annex4parser.legal_diff import LegalDiffAnalyzer, analyze_legal_changes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def setup_database():
    """Настроить базу данных."""
    # Создаём SQLite базу данных
    engine = create_engine("sqlite:///compliance_production.db")
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    return Session()


async def setup_alerts():
    """Настроить систему алертов."""
    # Инициализируем эмиттер алертов (без внешних сервисов для демо)
    emitter = get_alert_emitter(
        webhook_url=None,  # Отключаем webhook для демо
        kafka_bootstrap_servers=None,  # Отключаем Kafka для демо
        kafka_topic="rule-update"
    )
    
    logger.info("Alert system initialized (demo mode)")
    return emitter


async def run_monitoring_cycle():
    """Запустить цикл мониторинга."""
    try:
        # Настраиваем базу данных
        Session = await setup_database()
        
        # Настраиваем алерты
        emitter = await setup_alerts()
        
        with Session() as session:
            # Создаём монитор регуляторов
            monitor = RegulationMonitorV2(session)
            
            logger.info("Starting regulatory monitoring cycle...")
            
            # Обновляем все источники асинхронно
            stats = await monitor.update_all()
            
            logger.info(f"Monitoring cycle completed: {stats}")
            
            # Проверяем новые алерты
            from annex4parser.models import ComplianceAlert
            new_alerts = session.query(ComplianceAlert).filter_by(
                resolved_at=None
            ).order_by(ComplianceAlert.created_at.desc()).limit(10).all()
            
            for alert in new_alerts:
                logger.info(f"New alert: {alert.message} (Priority: {alert.priority})")
            
            return stats
    except Exception as e:
        logger.error(f"Monitoring cycle failed: {e}")
        return {"error": str(e)}


async def test_legal_diff():
    """Тестировать юридический diff-анализ."""
    analyzer = LegalDiffAnalyzer()
    
    # Тестовые тексты
    old_text = """
    Article 15.3 Documentation requirements
    
    Providers shall establish and maintain technical documentation 
    for high-risk AI systems in accordance with this Regulation.
    """
    
    new_text = """
    Article 15.3 Documentation requirements
    
    Providers shall establish and maintain comprehensive technical documentation 
    for high-risk AI systems in accordance with this Regulation, including 
    detailed risk assessments and mitigation strategies.
    """
    
    # Анализируем изменения
    change = analyzer.analyze_changes(old_text, new_text, "Article15.3")
    
    print("\n=== Legal Diff Analysis ===")
    print(f"Section: {change.section_code}")
    print(f"Change type: {change.change_type}")
    print(f"Severity: {change.severity}")
    print(f"Affected keywords: {change.keywords_affected}")
    print(f"Semantic similarity: {change.semantic_score:.2f}")
    print(f"Summary: {analyzer.get_change_summary(change)}")


async def test_eli_client():
    """Тестировать ELI SPARQL клиент."""
    from annex4parser.eli_client import fetch_regulation_by_celex
    
    logger.info("Testing ELI SPARQL client...")
    
    try:
        # Пытаемся получить EU AI Act
        result = await fetch_regulation_by_celex("32023R0988")
        
        if result:
            logger.info(f"Successfully fetched regulation: {result['title']}")
            logger.info(f"Version: {result['version']}")
            logger.info(f"Text length: {len(result['text'])} characters")
        else:
            logger.warning("No regulation found (this is expected in demo mode)")
            
    except Exception as e:
        logger.warning(f"ELI client test failed (expected in demo mode): {e}")


async def test_rss_monitoring():
    """Тестировать RSS мониторинг."""
    from annex4parser.rss_listener import fetch_rss_feed, REGULATORY_RSS_FEEDS
    
    logger.info("Testing RSS monitoring...")
    
    try:
        # Тестируем RSS пленарных заседаний Европарламента
        entries = await fetch_rss_feed(REGULATORY_RSS_FEEDS["ep_plenary"])
        
        logger.info(f"Fetched {len(entries)} RSS entries")
        
        for link, content_hash, title in entries[:3]:  # Показываем первые 3
            logger.info(f"Entry: {title}")
            logger.info(f"Link: {link}")
            logger.info(f"Hash: {content_hash[:16]}...")
            logger.info("-" * 50)
            
    except Exception as e:
        logger.warning(f"RSS monitoring test failed (expected in demo mode): {e}")


async def main():
    """Главная функция для запуска всех тестов."""
    print("🚀 Starting Annex4Parser Production Monitoring Demo")
    print("=" * 60)
    
    # Тестируем юридический diff
    await test_legal_diff()
    print()
    
    # Тестируем ELI клиент (может не работать без интернета)
    await test_eli_client()
    print()
    
    # Тестируем RSS мониторинг (может не работать без интернета)
    await test_rss_monitoring()
    print()
    
    # Запускаем полный цикл мониторинга
    print("🔄 Running full monitoring cycle...")
    stats = await run_monitoring_cycle()
    
    print("\n✅ Production monitoring demo completed!")
    print(f"📊 Final stats: {stats}")


if __name__ == "__main__":
    # Запускаем демо
    asyncio.run(main())
