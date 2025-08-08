# Annex4Parser - AI Compliance Document Parser

Система для автоматического анализа документов на соответствие требованиям EU AI Act и мониторинга регуляторных обновлений с production-grade архитектурой.

## 🚀 Features

- **Automatic document mapping** с EU AI Act требованиями
- **Semantic text analysis** для точного определения соответствия
- **Production-grade regulatory monitoring** с мультисорс-фетчингом
- **Support for various document formats** (PDF, DOCX)
- **Compliance database** с детальной аналитикой
- **Event-driven alerts** через Kafka и webhooks
- **Legal-aware diff analysis** для классификации изменений
- **Async multi-source fetching** (ELI SPARQL, RSS, HTML)

## 📋 Requirements

- Python 3.8+
- SQLite (built into Python) или PostgreSQL для production
- Internet connection для загрузки регуляций
- Kafka (опционально, для event-driven алертов)

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
# Run all tests (fast execution)
python -m pytest tests/ -v --tb=short

# Expected output: 133 passed, 21 skipped in ~7 seconds
# Note: 21 tests in test_retry.py are intentionally skipped
```

All tests should pass successfully.

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

### 2. Load regulations (Legacy)

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

### 3. Production-grade monitoring (New!)

```python
import asyncio
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2

async def run_production_monitoring():
    with Session() as session:
        # Создаём production-grade монитор
        monitor = RegulationMonitorV2(session)
        
        # Обновляем все источники асинхронно
        stats = await monitor.update_all()
        print(f"Monitoring completed: {stats}")

# Запускаем
asyncio.run(run_production_monitoring())
```

### 4. Analyze document

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

## 🆕 Production-Grade Components

### 1. Multi-Source Monitoring

```python
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2

# Автоматически поддерживает:
# - ELI SPARQL (EUR-Lex API)
# - RSS feeds (EUR-Lex, EP, EC)
# - HTML sources (fallback)
# - Async processing
# - Retry logic с exponential back-off
```

### 2. Legal Diff Analysis

```python
from annex4parser.legal_diff import LegalDiffAnalyzer, analyze_legal_changes

analyzer = LegalDiffAnalyzer()

# Анализируем изменения
change = analyzer.analyze_changes(
    old_text="Providers shall maintain documentation.",
    new_text="Providers must maintain comprehensive documentation.",
    section_code="Article15.3"
)

print(f"Change type: {change.change_type}")
print(f"Severity: {change.severity}")
print(f"Affected keywords: {change.keywords_affected}")
```

### 3. Event-Driven Alerts

```python
from annex4parser.alerts import AlertEmitter, emit_rule_changed

# Настраиваем алерты
emitter = AlertEmitter(
    webhook_url="https://your-domain.com/webhook",
    kafka_bootstrap_servers="localhost:9092"
)

# Эмитируем алерт
emit_rule_changed(
    rule_id="rule-123",
    severity="major",
    regulation_name="EU AI Act",
    section_code="Article15.3"
)
```

### 4. ELI SPARQL Client

```python
from annex4parser.eli_client import fetch_regulation_by_celex

# Получаем регуляцию через ELI API
result = await fetch_regulation_by_celex("32023R0988")
if result:
    print(f"Title: {result['title']}")
    print(f"Version: {result['version']}")
    print(f"Text length: {len(result['text'])} chars")
```

### 5. RSS Monitoring

```python
from annex4parser.rss_listener import fetch_rss_feed, RSSMonitor

# Получаем RSS-фид
entries = await fetch_rss_feed("https://eur-lex.europa.eu/legal-content/EN/RSS/?type=latestLegislation")

# Мониторим изменения
monitor = RSSMonitor()
new_entries = await monitor.check_for_updates("https://example.com/rss")
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

### Production Monitoring

```python
import asyncio
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.alerts import get_alert_emitter

async def production_workflow():
    with Session() as session:
        # Инициализируем алерты
        emitter = get_alert_emitter(
            webhook_url="https://your-domain.com/webhook",
            kafka_bootstrap_servers="localhost:9092"
        )
        
        # Создаём монитор
        monitor = RegulationMonitorV2(session)
        
        # Запускаем мониторинг
        stats = await monitor.update_all()
        
        # Проверяем новые алерты
        from annex4parser.models import ComplianceAlert
        new_alerts = session.query(ComplianceAlert).filter_by(
            resolved_at=None
        ).order_by(ComplianceAlert.created_at.desc()).limit(10).all()
        
        for alert in new_alerts:
            print(f"⚠️ {alert.message} (Priority: {alert.priority})")

# Запускаем
asyncio.run(production_workflow())
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
# Production monitoring tests
python -m pytest tests/test_production_monitoring.py -v

# Legal diff tests
python -m pytest tests/test_production_monitoring.py::TestLegalDiffAnalyzer -v

# Alert system tests
python -m pytest tests/test_production_monitoring.py::TestAlertEmitter -v
```

### Functionality testing

```python
# Production monitoring demo
python examples/production_monitoring.py

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
- **sources** - Regulatory sources (ELI, RSS, HTML)
- **reg_source_log** - Source operation logs

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

# Source statistics
from annex4parser.models import Source, RegulationSourceLog
sources = session.query(Source).filter_by(active=True).all()
for source in sources:
    logs = session.query(RegulationSourceLog).filter_by(source_id=source.id).all()
    print(f"{source.id}: {len(logs)} operations")
```

## 🔧 Configuration

### Sources configuration

```yaml
# sources.yaml
sources:
  - id: celex_consolidated
    url: "https://eur-lex.europa.eu/eli-register?uri=eli%3a%2f%2flaw%2fregulation%2f2024%2f1689"
    type: eli_sparql
    freq: "6h"
    celex_id: "32024R1689"
    
  - id: eurlex_latest_rss
    url: "https://eur-lex.europa.eu/legal-content/EN/RSS/?type=latestLegislation"
    type: rss
    freq: "instant"
```

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

### Issue: "Kafka connection failed"
```python
# Check Kafka configuration
from annex4parser.alerts import AlertEmitter

emitter = AlertEmitter(
    kafka_bootstrap_servers="localhost:9092",
    kafka_topic="rule-update"
)
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

### Async processing

```python
import asyncio
from annex4parser.regulation_monitor_v2 import update_all_regulations

# Асинхронное обновление всех источников
async def update_all():
    with Session() as session:
        stats = await update_all_regulations(session)
        print(f"Updated: {stats}")

asyncio.run(update_all())
```

## 🚀 Production Deployment

Для production развертывания смотрите [DEPLOYMENT.md](DEPLOYMENT.md).

### Docker Compose

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: compliance_production
      POSTGRES_USER: compliance_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  kafka:
    image: confluentinc/cp-kafka:7.0.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092

  annex4parser:
    build: .
    depends_on:
      - postgres
      - kafka
    environment:
      - DATABASE_URL=postgresql://compliance_user:secure_password@postgres/compliance_production
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092

volumes:
  postgres_data:
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
# Run production monitoring demo
python examples/production_monitoring.py

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

**Annex4Parser** - automate AI regulatory compliance with production-grade architecture! 🤖✨
