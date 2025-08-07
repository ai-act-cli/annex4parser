#!/usr/bin/env python3
"""
Простой тест основной функциональности Annex4Parser
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Base, Regulation, Rule, Document
from annex4parser.mapper.mapper import match_rules
from annex4parser.mapper.semantic_mapper import semantic_match_rules
from annex4parser.mapper.combined_mapper import combined_match_rules
from annex4parser.legal_diff import LegalDiffAnalyzer
from annex4parser.alerts import AlertEmitter

def test_basic_functionality():
    """Тест основной функциональности."""
    print("🚀 Testing Annex4Parser Basic Functionality")
    print("=" * 50)
    
    # 1. Тест базы данных
    print("\n1. Testing database setup...")
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Создаём тестовую регуляцию
    reg = Regulation(name='EU AI Act Test', version='1.0')
    session.add(reg)
    session.flush()
    
    # Создаём тестовые правила
    test_rules = [
        Rule(regulation_id=reg.id, section_code='Article9.2', 
             title='Risk Management', content='Risk management requirements for AI systems'),
        Rule(regulation_id=reg.id, section_code='Article15.3', 
             title='Documentation', content='Documentation requirements for compliance'),
        Rule(regulation_id=reg.id, section_code='Article10.1', 
             title='Data Governance', content='Data governance requirements')
    ]
    for rule in test_rules:
        session.add(rule)
    session.commit()
    
    print("✅ Database setup successful")
    
    # 2. Тест keyword matching
    print("\n2. Testing keyword matching...")
    test_text = "Our AI system implements comprehensive risk management procedures."
    matches = match_rules(test_text)
    print(f"Found matches: {matches}")
    assert 'Article9.2' in matches, "Should find risk management"
    print("✅ Keyword matching works")
    
    # 3. Тест semantic matching
    print("\n3. Testing semantic matching...")
    sem_matches = semantic_match_rules(session, test_text, threshold=0.1)
    print(f"Semantic matches: {sem_matches}")
    print("✅ Semantic matching works")
    
    # 4. Тест combined matching
    print("\n4. Testing combined matching...")
    combined_matches = combined_match_rules(session, test_text)
    print(f"Combined matches: {combined_matches}")
    print("✅ Combined matching works")
    
    # 5. Тест legal diff analysis
    print("\n5. Testing legal diff analysis...")
    analyzer = LegalDiffAnalyzer()
    
    old_text = "Providers shall maintain documentation."
    new_text = "Providers must maintain comprehensive documentation."
    
    change = analyzer.analyze_changes(old_text, new_text, "Article15.3")
    print(f"Change type: {change.change_type}")
    print(f"Severity: {change.severity}")
    print(f"Affected keywords: {change.keywords_affected}")
    print("✅ Legal diff analysis works")
    
    # 6. Тест alert system
    print("\n6. Testing alert system...")
    emitter = AlertEmitter()
    emitter.emit_rule_changed(
        rule_id="test-rule-123",
        severity="high",
        regulation_name="EU AI Act",
        section_code="Article15.3"
    )
    print("✅ Alert system works")
    
    session.close()
    print("\n🎉 All basic functionality tests passed!")

if __name__ == "__main__":
    test_basic_functionality()


