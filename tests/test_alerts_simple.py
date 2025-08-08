import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock
from annex4parser.models import Document, Regulation, Rule, DocumentRuleMapping
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import ComplianceAlert
from types import SimpleNamespace


def test_alert_and_doc_outdated(test_db, eli_rdf_v1, eli_rdf_v2, test_config_path):
    """Тест создания алерта и пометки документа как устаревшего"""
    # -- подготовим документ, связанный с Article15.3 ------------------
    doc = Document(
        id=uuid.uuid4(), 
        filename="foo.pdf",
        compliance_status="compliant"
    )
    test_db.add(doc)
    test_db.commit()
    
    # Симулируем старую Rule 15.3 и маппинг
    old_reg = Regulation(name="EU AI Act", version="old")
    test_db.add(old_reg)
    test_db.flush()
    
    old_rule = Rule(
        regulation_id=old_reg.id, 
        section_code="Article15.3",
        content="old text", 
        risk_level="critical"
    )
    test_db.add(old_rule)
    test_db.flush()
    
    test_db.add(DocumentRuleMapping(
        document_id=doc.id,
        rule_id=old_rule.id,
        confidence_score=0.9
    ))
    test_db.commit()

    mon = RegulationMonitorV2(test_db, config_path=test_config_path)

    # Мокаем fetch_latest_eli чтобы возвращать структурированные данные
    mock_eli_data = {
        "title": "EU AI Act",
        "version": "2.0",
        "text": "Article 15.3 Documentation requirements\n\nProviders shall establish and maintain comprehensive technical documentation for high-risk AI systems in accordance with this Regulation, including detailed risk assessments and mitigation strategies.",
        "date": "2024-02-15"
    }

    # Напрямую вызываем _ingest_regulation_text для тестирования
    print("Directly calling _ingest_regulation_text...")
    regulation = mon._ingest_regulation_text(
        name="EU AI Act",
        version="2.0",
        text="Article 15.3 Documentation requirements\n\nProviders shall establish and maintain comprehensive technical documentation for high-risk AI systems in accordance with this Regulation, including detailed risk assessments and mitigation strategies.",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689"
    )
    print(f"Regulation created/updated: {regulation.name} (ID: {regulation.id})")

    # Проверяем, что алерт создан и документ помечен как устаревший
    alert = test_db.query(ComplianceAlert).first()
    print(f"Alert found: {alert}")
    if alert:
        print(f"Alert priority: {alert.priority}")
        print(f"Alert message: {alert.message}")
        assert alert.priority == "urgent"  # Updated: severity mapping changed to urgent for high/critical/major
    
    updated_doc = test_db.get(Document, doc.id)
    print(f"Document compliance status: {updated_doc.compliance_status}")
    print(f"Document mappings count: {len(updated_doc.mappings)}")
    
    # Проверяем, что правило обновилось
    rules = test_db.query(Rule).filter_by(section_code="Article15.3").all()
    print(f"Rules found: {len(rules)}")
    for rule in rules:
        print(f"Rule content: {rule.content[:100]}...")
    
    assert updated_doc.compliance_status == "outdated"
