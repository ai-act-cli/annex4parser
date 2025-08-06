#!/usr/bin/env python3
"""
Annex4Parser Basic Usage Examples
"""

import sys
import os
from pathlib import Path

# Add root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Base, Regulation, Rule, Document
from annex4parser.mapper.mapper import match_rules
from annex4parser.mapper.semantic_mapper import semantic_match_rules
from annex4parser.mapper.combined_mapper import combined_match_rules
from annex4parser.document_ingestion import ingest_document
from annex4parser.regulation_monitor import RegulationMonitor

def setup_database():
    """Create and setup database"""
    print("🔧 Setting up database...")
    
    # Create database
    engine = create_engine("sqlite:///example_compliance.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    session = Session()
    
    # Create test regulation
    reg = Regulation(
        name="EU AI Act Test",
        version="2024.1",
        source_url="https://example.com/ai-act",
        status="active"
    )
    session.add(reg)
    session.flush()
    
    # Create test rules
    test_rules = [
        {
            'section_code': 'Article9.2',
            'title': 'Risk Management System',
            'content': 'Providers of high-risk AI systems shall establish, implement, document and maintain a risk management system.'
        },
        {
            'section_code': 'Article10.1',
            'title': 'Data Governance',
            'content': 'Providers shall ensure that the AI system is trained, validated and tested on data sets that meet quality criteria.'
        },
        {
            'section_code': 'Article15.3',
            'title': 'Documentation Requirements',
            'content': 'Providers shall draw up the technical documentation of the high-risk AI system.'
        },
        {
            'section_code': 'Article16.1',
            'title': 'Accuracy and Cybersecurity',
            'content': 'High-risk AI systems shall be designed to achieve appropriate levels of accuracy, robustness and cybersecurity.'
        }
    ]
    
    for rule_data in test_rules:
        rule = Rule(
            regulation_id=reg.id,
            section_code=rule_data['section_code'],
            title=rule_data['title'],
            content=rule_data['content'],
            risk_level='high',
            version='2024.1'
        )
        session.add(rule)
    
    session.commit()
    print(f"✅ Created {len(test_rules)} rules")
    
    return session

def example_keyword_matching():
    """Keyword search example"""
    print("\n🔍 Keyword search example:")
    
    test_texts = [
        "Our AI system implements comprehensive risk management procedures.",
        "The system uses high-quality training data with proper governance.",
        "We maintain detailed documentation for all AI operations."
    ]
    
    for i, text in enumerate(test_texts, 1):
        matches = match_rules(text)
        print(f"\nText {i}: {text[:50]}...")
        print(f"Found matches: {matches}")

def example_semantic_matching(session):
    """Semantic analysis example"""
    print("\n🧠 Semantic analysis example:")
    
    test_text = "Our organization has implemented comprehensive risk assessment procedures for AI systems."
    
    matches = semantic_match_rules(session, test_text, threshold=0.1)
    print(f"Text: {test_text}")
    print(f"Semantic matches: {matches}")

def example_combined_matching(session):
    """Combined analysis example"""
    print("\n⚡ Combined analysis example:")
    
    test_text = "Our AI system implements risk management and maintains proper documentation."
    
    matches = combined_match_rules(session, test_text)
    print(f"Text: {test_text}")
    print(f"Combined matches: {matches}")

def example_document_ingestion(session):
    """Document ingestion example"""
    print("\n📄 Document ingestion example:")
    
    # Create temporary file
    import tempfile
    import docx
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc = docx.Document()
    doc.add_paragraph("Our AI system implements comprehensive risk management procedures. We maintain detailed documentation and ensure data governance protocols are followed.")
    doc.save(temp_file.name)
    temp_file.close()
    
    try:
        # Load document
        doc_record = ingest_document(Path(temp_file.name), session)
        
        print(f"Document: {doc_record.filename}")
        print(f"Found matches: {len(doc_record.mappings)}")
        
        for mapping in doc_record.mappings:
            print(f"  - {mapping.rule.section_code}: {mapping.confidence_score:.2f}")
            
    finally:
        # Cleanup
        os.unlink(temp_file.name)

def example_regulation_monitoring(session):
    """Regulation monitoring example"""
    print("\n📊 Regulation monitoring example:")
    
    monitor = RegulationMonitor(session)
    
    # Check monitoring methods
    print(f"✓ Monitoring created")
    print(f"✓ Update method: {hasattr(monitor, 'update')}")
    print(f"✓ Compute_diff method: {hasattr(monitor, 'compute_diff')}")
    
    # Test diff utilities
    old_text = "Original content"
    new_text = "Updated content with changes"
    diff = monitor.compute_diff(old_text, new_text)
    change_type = monitor.classify_change(diff)
    
    print(f"✓ Diff utilities working (change type: {change_type})")

def main():
    """Main function with examples"""
    print("🚀 Annex4Parser - Usage Examples")
    print("=" * 50)
    
    # Setup database
    session = setup_database()
    
    try:
        # Run examples
        example_keyword_matching()
        example_semantic_matching(session)
        example_combined_matching(session)
        example_document_ingestion(session)
        example_regulation_monitoring(session)
        
        print("\n✅ All examples completed successfully!")
        
    finally:
        session.close()

if __name__ == "__main__":
    main()

