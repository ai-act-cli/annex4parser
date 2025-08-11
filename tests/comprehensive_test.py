#!/usr/bin/env python3
"""
Comprehensive test of the entire annex4parser system
"""

import tempfile
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Base, Regulation, Rule, Document, DocumentRuleMapping, ComplianceAlert
from annex4parser.mapper.mapper import match_rules, DEFAULT_KEYWORD_MAP
from annex4parser.mapper.semantic_mapper import semantic_match_rules
from annex4parser.mapper.combined_mapper import combined_match_rules
from annex4parser.document_ingestion import ingest_document
from annex4parser.regulation_monitor import RegulationMonitor

def test_keyword_matching():
    """Test keyword matching with real content"""
    print("\n=== Testing Keyword Matching ===")
    
    test_cases = [
        {
            'text': 'Our AI system implements comprehensive risk management procedures to ensure safety.',
            'expected': ['Article9.2']
        },
        {
            'text': 'The system uses high-quality training data with proper data governance protocols.',
            'expected': ['Article10.1']
        },
        {
            'text': 'We maintain detailed documentation and record keeping for all AI operations.',
            'expected': ['Article11', 'Article12']
        },
        {
            'text': 'Our AI achieves high accuracy and maintains robust cybersecurity measures.',
            'expected': ['Article15']
        },
        {
            'text': 'Human oversight is maintained throughout all AI system operations.',
            'expected': ['Article14']
        }
    ]
    
    passed = 0
    for i, case in enumerate(test_cases, 1):
        try:
            matches = match_rules(case['text'])
            found = list(matches.keys())
            expected = case['expected']
            
            print(f"\nTest {i}: {case['text'][:50]}...")
            print(f"Expected: {expected}")
            print(f"Found: {found}")
            
            if any(exp in found for exp in expected):
                print("✓ PASS")
                passed += 1
            else:
                print("✗ FAIL")
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    print(f"\nKeyword matching: {passed}/{len(test_cases)} tests passed")
    assert passed > 0, f"Only {passed}/{len(test_cases)} keyword matching tests passed"

def test_semantic_matching(test_db, test_regulation):
    """Test semantic matching with real content"""
    print("\n=== Testing Semantic Matching ===")
    
    test_cases = [
        {
            'text': 'Our organization has implemented comprehensive risk assessment procedures for AI systems.',
            'expected_sections': ['Article9.2']
        },
        {
            'text': 'We ensure our training datasets are representative and free of bias.',
            'expected_sections': ['Article10.1']
        },
        {
            'text': 'Technical documentation is maintained for all AI system components.',
            'expected_sections': ['Article11']
        },
        {
            'text': 'System logs are preserved for audit and compliance purposes.',
            'expected_sections': ['Article12']
        }
    ]
    
    passed = 0
    for i, case in enumerate(test_cases, 1):
        try:
            matches = semantic_match_rules(test_db, case['text'], threshold=0.1)
            found = list(matches.keys())
            expected = case['expected_sections']
            
            print(f"\nTest {i}: {case['text'][:50]}...")
            print(f"Expected: {expected}")
            print(f"Found: {found}")
            print(f"Scores: {matches}")
            
            if any(exp in found for exp in expected):
                print("✓ PASS")
                passed += 1
            else:
                print("✗ FAIL")
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    print(f"\nSemantic matching: {passed}/{len(test_cases)} tests passed")
    assert passed > 0, f"Only {passed}/{len(test_cases)} semantic matching tests passed"

def test_combined_matching(test_db, test_regulation):
    """Test combined keyword and semantic matching"""
    print("\n=== Testing Combined Matching ===")
    
    test_cases = [
        {
            'text': 'Our AI system implements risk management and maintains proper documentation.',
            'expected_sections': ['Article9.2', 'Article11']
        },
        {
            'text': 'Data governance ensures high-quality training datasets with accurate results.',
            'expected_sections': ['Article10.1', 'Article15']
        }
    ]
    
    passed = 0
    for i, case in enumerate(test_cases, 1):
        try:
            matches = combined_match_rules(test_db, case['text'])
            found = list(matches.keys())
            expected = case['expected_sections']
            
            print(f"\nTest {i}: {case['text'][:50]}...")
            print(f"Expected: {expected}")
            print(f"Found: {found}")
            print(f"Combined scores: {matches}")
            
            if any(exp in found for exp in expected):
                print("✓ PASS")
                passed += 1
            else:
                print("✗ FAIL")
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    print(f"\nCombined matching: {passed}/{len(test_cases)} tests passed")
    assert passed > 0, f"Only {passed}/{len(test_cases)} combined matching tests passed"

def test_document_ingestion(test_db, test_regulation):
    """Test document ingestion with real content"""
    print("\n=== Testing Document Ingestion ===")
    
    test_documents = [
        {
            'content': 'Our AI system implements comprehensive risk management procedures. We maintain detailed documentation and ensure data governance protocols are followed.',
            'expected_mappings': 3  # Should map to Article9.2, Article11, Article10.1
        },
        {
            'content': 'The system achieves high accuracy and maintains robust cybersecurity measures. Human oversight is maintained throughout operations.',
            'expected_mappings': 2  # Should map to Article15, Article14
        }
    ]
    
    passed = 0
    for i, doc_data in enumerate(test_documents, 1):
        try:
            # Create temporary file for ingestion
            import tempfile
            import docx
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
            doc = docx.Document()
            doc.add_paragraph(doc_data['content'])
            doc.save(temp_file.name)
            temp_file.close()

            # Ingest document
            doc_record = ingest_document(Path(temp_file.name), test_db)
            mappings = doc_record.mappings

            # Cleanup
            import os
            os.unlink(temp_file.name)
            
            print(f"\nTest {i}: {doc_data['content'][:50]}...")
            print(f"Expected mappings: {doc_data['expected_mappings']}")
            print(f"Actual mappings: {len(mappings)}")
            print(f"Mappings: {[(m.rule.section_code, m.confidence_score) for m in mappings]}")
            
            if len(mappings) >= doc_data['expected_mappings']:
                print("✓ PASS")
                passed += 1
            else:
                print("✗ FAIL")
                
        except Exception as e:
            print(f"✗ ERROR: {e}")
    
    print(f"\nDocument ingestion: {passed}/{len(test_documents)} tests passed")
    assert passed > 0, f"Only {passed}/{len(test_documents)} document ingestion tests passed"

def test_regulation_monitoring(test_db, test_regulation):
    """Test regulation monitoring functionality"""
    print("\n=== Testing Regulation Monitoring ===")
    
    try:
        # Create monitor
        monitor = RegulationMonitor(test_db)
        
        # Test that monitor can be created and has expected methods
        assert hasattr(monitor, 'update'), "Monitor should have update method"
        assert hasattr(monitor, 'compute_diff'), "Monitor should have compute_diff method"
        assert hasattr(monitor, 'classify_change'), "Monitor should have classify_change method"
        
        print("✓ Regulation monitor created successfully")
        
        # Test diff utilities
        old_text = "Original content"
        new_text = "Updated content with changes"
        diff = monitor.compute_diff(old_text, new_text)
        assert len(diff) > 0, "Diff should not be empty"
        
        change_type = monitor.classify_change(diff)
        assert change_type in ['major', 'minor', 'clarification'], f"Invalid change type: {change_type}"
        
        print("✓ Diff utilities work correctly")
        
        # Test that we can create a new regulation
        reg = Regulation(
            name='Test Regulation',
            celex_id='TEST123',
            version='2.0',
            source_url='https://example.com/test',
            status='active'
        )
        test_db.add(reg)
        test_db.commit()
        
        print("✓ Can create new regulations")
        
    except Exception as e:
        print(f"✗ Regulation monitoring test failed: {e}")
        assert False, f"Regulation monitoring test failed: {e}"
