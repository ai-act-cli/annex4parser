#!/usr/bin/env python3
"""
Simple test script to verify basic functionality
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_keyword_matching():
    """Test the keyword matching functionality"""
    print("=== Testing Keyword Matching ===")
    
    # Import here to avoid import issues
    from annex4parser.mapper.mapper import match_rules, KEYWORD_MAP
    
    test_text = "This document covers risk management and documentation requirements."
    matches = match_rules(test_text)
    
    print(f"Test text: {test_text}")
    print(f"Available keywords: {list(KEYWORD_MAP.keys())}")
    print(f"Found matches: {matches}")
    
    # Check if expected matches are found
    expected_matches = ['Article9.2', 'Article15.3']
    for expected in expected_matches:
        if expected in matches:
            print(f"✓ Found {expected}")
        else:
            print(f"✗ Missing {expected}")
    
    assert len(matches) > 0, f"Expected to find matches, but found: {matches}"

def test_database_models():
    """Test database model creation"""
    print("\n=== Testing Database Models ===")
    
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from annex4parser.models import Base, Regulation, Rule
        
        # Create in-memory database
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Create test data
        reg = Regulation(name='EU AI Act', version='1.0')
        session.add(reg)
        session.flush()
        
        rule = Rule(
            regulation_id=reg.id,
            section_code='Article9.2',
            title='Risk Management',
            content='Risk management requirements'
        )
        session.add(rule)
        session.commit()
        
        # Query test
        rules = session.query(Rule).all()
        print(f"✓ Created {len(rules)} rules in database")
        
        session.close()
        assert len(rules) > 0, "No rules were created in database"
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        assert False, f"Database test failed: {e}"

def test_semantic_matching():
    """Test semantic matching functionality"""
    print("\n=== Testing Semantic Matching ===")
    
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from annex4parser.models import Base, Regulation, Rule
        from annex4parser.mapper.semantic_mapper import semantic_match_rules
        
        # Setup database
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Create test data
        reg = Regulation(name='EU AI Act', version='1.0')
        session.add(reg)
        session.flush()
        
        rule = Rule(
            regulation_id=reg.id,
            section_code='Article9.2',
            title='Risk Management',
            content='Risk management requirements for AI systems'
        )
        session.add(rule)
        session.commit()
        
        # Test semantic matching
        test_text = "This document discusses risk management procedures."
        matches = semantic_match_rules(session, test_text, threshold=0.1)
        
        print(f"Test text: {test_text}")
        print(f"Semantic matches: {matches}")
        
        session.close()
        assert len(matches) > 0, f"Expected semantic matches, but found: {matches}"
        
    except Exception as e:
        print(f"✗ Semantic matching test failed: {e}")
        assert False, f"Semantic matching test failed: {e}"

def main():
    """Run all tests"""
    print("Starting functionality tests...\n")
    
    tests = [
        test_keyword_matching,
        test_database_models,
        test_semantic_matching
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠ Some tests failed")

if __name__ == "__main__":
    main()
