# Annex4Parser - AI Compliance Document Parser

A system for automatic analysis of documents for compliance with EU AI Act requirements and monitoring regulatory updates.

## 🚀 Features

- **Automatic document mapping** with EU AI Act requirements
- **Semantic text analysis** for accurate compliance determination
- **Regulatory update monitoring** with automatic notifications
- **Support for various document formats** (PDF, DOCX)
- **Compliance database** with detailed analytics

## 📋 Requirements

- Python 3.8+
- SQLite (built into Python)
- Internet connection for downloading regulations

## 🔧 Installation

### Step 1: Clone the repository

```bash
git clone <repository-url>
cd a4p
```

### Step 2: Create virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Verify installation

```bash
python -m pytest tests/ -v
```

All tests should pass successfully (12 passed).

## 🏃‍♂️ Quick Start

### 1. Initialize database

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Base

# Create database
engine = create_engine("sqlite:///compliance.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
```

### 2. Load regulations

```python
from annex4parser.regulation_monitor import RegulationMonitor

with Session() as session:
    monitor = RegulationMonitor(session)
    
    # Load EU AI Act
    regulation = monitor.update(
        name="EU AI Act",
        version="2024.1",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R0988"
    )
    print(f"Loaded {len(regulation.rules)} rules")
```

### 3. Analyze document

```python
from pathlib import Path
from annex4parser.document_ingestion import ingest_document

with Session() as session:
    # Analyze document
    doc_record = ingest_document(
        Path("your_document.pdf"), 
        session
    )
    
    print(f"Document: {doc_record.filename}")
    print(f"Found matches: {len(doc_record.mappings)}")
    
    # Detailed information about matches
    for mapping in doc_record.mappings:
        print(f"- {mapping.rule.section_code}: {mapping.confidence_score:.2f}")
```

## 📖 Detailed Guide

### Compliance Analysis

#### Keyword Matching

```python
from annex4parser.mapper.mapper import match_rules

text = "Our AI system implements comprehensive risk management procedures."
matches = match_rules(text)
print(matches)
# Output: {'Article9.2': 0.8}
```

#### Semantic Matching

```python
from annex4parser.mapper.semantic_mapper import semantic_match_rules

with Session() as session:
    matches = semantic_match_rules(session, text, threshold=0.1)
    print(matches)
    # Output: {'Article9.2': 0.25, 'Article15.3': 0.18}
```

#### Combined Matching

```python
from annex4parser.mapper.combined_mapper import combined_match_rules

with Session() as session:
    matches = combined_match_rules(session, text)
    print(matches)
    # Output: {'Article9.2': 0.65, 'Article15.3': 0.42}
```

### Regulatory Update Monitoring

```python
from annex4parser.regulation_monitor import RegulationMonitor
from annex4parser.models import ComplianceAlert

with Session() as session:
    monitor = RegulationMonitor(session)
    
    # Check for updates
    updated_reg = monitor.update(
        name="EU AI Act",
        version="2024.2", 
        url="https://updated-regulation-url.com"
    )
    
    # Check for new alerts
    alerts = session.query(ComplianceAlert).filter_by(
        alert_type="rule_updated"
    ).all()
    
    for alert in alerts:
        print(f"⚠️ {alert.message} (Priority: {alert.priority})")
```

### Database Operations

#### Creating regulations

```python
from annex4parser.models import Regulation, Rule

with Session() as session:
    # Create regulation
    reg = Regulation(
        name="EU AI Act",
        version="2024.1",
        source_url="https://example.com",
        status="active"
    )
    session.add(reg)
    session.flush()
    
    # Add rules
    rule = Rule(
        regulation_id=reg.id,
        section_code="Article9.2",
        title="Risk Management System",
        content="Providers shall establish risk management systems...",
        risk_level="high"
    )
    session.add(rule)
    session.commit()
```

#### Creating documents

```python
from annex4parser.models import Document, DocumentRuleMapping

with Session() as session:
    # Create document
    doc = Document(
        filename="risk_assessment.pdf",
        file_path="/path/to/document.pdf",
        ai_system_name="Medical AI System",
        document_type="risk_assessment"
    )
    session.add(doc)
    session.flush()
    
    # Create mapping
    mapping = DocumentRuleMapping(
        document_id=doc.id,
        rule_id=rule.id,
        confidence_score=0.85,
        mapped_by="auto"
    )
    session.add(mapping)
    session.commit()
```

## 🧪 Testing

### Run all tests

```bash
python -m pytest tests/ -v
```

### Run specific tests

```bash
# Keyword tests
python -m pytest tests/simple_test.py::test_keyword_matching -v

# Semantic analysis tests
python -m pytest tests/comprehensive_test.py::test_semantic_matching -v

# Document ingestion tests
python -m pytest tests/test_ingestion.py -v
```

### Functionality testing

```python
# Simple system test
python tests/simple_test.py

# Comprehensive test
python tests/comprehensive_test.py
```

## 📊 Database Structure

### Main tables

- **regulations** - Regulations (EU AI Act, etc.)
- **rules** - Regulation rules (articles)
- **documents** - Uploaded documents
- **document_rules** - Document-rule relationships
- **compliance_alerts** - Change notifications

### Query examples

```python
# All documents with their matches
documents = session.query(Document).all()
for doc in documents:
    print(f"Document: {doc.filename}")
    for mapping in doc.mappings:
        print(f"  - {mapping.rule.section_code}: {mapping.confidence_score}")

# High-risk documents
high_risk_docs = session.query(Document).join(
    DocumentRuleMapping
).join(Rule).filter(
    Rule.risk_level == "high"
).all()

# Recent alerts
recent_alerts = session.query(ComplianceAlert).filter(
    ComplianceAlert.created_at >= datetime.now() - timedelta(days=7)
).all()
```

## 🔧 Configuration

### Cache configuration

```python
from pathlib import Path

# Configure cache directory
cache_dir = Path("./cache")
monitor = RegulationMonitor(session, cache_dir=cache_dir)
```

### Semantic analysis threshold configuration

```python
# Stricter threshold
matches = semantic_match_rules(session, text, threshold=0.3)

# More lenient threshold
matches = semantic_match_rules(session, text, threshold=0.05)
```

## 🚨 Troubleshooting

### Issue: "Module not found"
```bash
# Make sure you're in the correct directory
cd a4p
pip install -r requirements.txt
```

### Issue: "Database locked"
```python
# Close all database connections
session.close()
engine.dispose()
```

### Issue: "No matches found"
```python
# Check that rules are loaded
rules = session.query(Rule).all()
print(f"Loaded rules: {len(rules)}")

# Try lowering the threshold
matches = semantic_match_rules(session, text, threshold=0.05)
```

## 📈 Performance

### Optimization for large documents

```python
# Process large files in chunks
def process_large_document(file_path, session, chunk_size=1000):
    with open(file_path, 'r') as f:
        text = f.read()
    
    # Split into chunks
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        matches = combined_match_rules(session, chunk)
        print(f"Chunk {i+1}: {len(matches)} matches")
```

### Caching results

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_semantic_match(text):
    return semantic_match_rules(session, text, threshold=0.1)
```

## 🤝 Contributing

1. Fork the repository
2. Create a branch for your feature
3. Add tests
4. Run tests: `python -m pytest tests/ -v`
5. Create a Pull Request

## 📄 License

MIT License

## 📚 Additional Documentation

- **[Usage Examples](examples/README.md)** - ready-to-use code examples
- **[Deployment Guide](DEPLOYMENT.md)** - production deployment
- **[Tests](tests/)** - complete system test suite

## 🧪 Running Examples

```bash
# Run basic examples
python examples/basic_usage.py

# Run all tests
python -m pytest tests/ -v
```

## 📞 Support

- Create an Issue for bugs
- Use Discussions for questions
- Check documentation in the `docs/` folder

---

**Annex4Parser** - automate AI regulatory compliance! 🤖✨
