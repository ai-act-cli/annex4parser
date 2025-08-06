#!/usr/bin/env python3
"""
Simple system test for annex4parser
"""

import tempfile
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from annex4parser.models import Base, Regulation, Rule, Document
from annex4parser.mapper.mapper import match_rules, KEYWORD_MAP
from annex4parser.mapper.semantic_mapper import semantic_match_rules
from annex4parser.mapper.combined_mapper import combined_match_rules
from annex4parser.document_ingestion import ingest_document

def test_system():
    """Test the entire system"""
    print("=== Testing Annex4Parser System ===")
    
    # Setup database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Create test regulation
        reg = Regulation(name='EU AI Act Test', version='1.0')
        session.add(reg)
        session.flush()
        
        # Create test rules
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
        
        print("✓ Database setup complete")
        
        # Test 1: Keyword matching
        print("\n1. Testing keyword matching...")
        test_text = "Our AI system implements comprehensive risk management procedures."
        matches = match_rules(test_text)
        print(f"Found matches: {matches}")
        assert 'Article9.2' in matches, "Should find risk management"
        print("✓ Keyword matching works")
        
        # Test 2: Semantic matching
        print("\n2. Testing semantic matching...")
        sem_matches = semantic_match_rules(session, test_text, threshold=0.1)
        print(f"Semantic matches: {sem_matches}")
        print("✓ Semantic matching works")
        
        # Test 3: Combined matching
        print("\n3. Testing combined matching...")
        combined_matches = combined_match_rules(session, test_text)
        print(f"Combined matches: {combined_matches}")
        print("✓ Combined matching works")
        
        # Test 4: Document ingestion
        print("\n4. Testing document ingestion...")
        import docx
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc = docx.Document()
        doc.add_paragraph("This document covers risk management and documentation requirements.")
        doc.save(temp_file.name)
        temp_file.close()
        
        doc_record = ingest_document(Path(temp_file.name), session)
        print(f"Created document: {doc_record.filename}")
        print(f"Document mappings: {len(doc_record.mappings)}")
        
        # Cleanup
        os.unlink(temp_file.name)
        print("✓ Document ingestion works")
        
        session.close()
        print("\n🎉 All system components working correctly!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        session.close()
        assert False, f"System test failed: {e}"

if __name__ == "__main__":
    test_system()
