# 🚀 Annex4Parser Quick Start

**Annex4Parser** - a system for automatic analysis of documents for compliance with EU AI Act requirements.

## ⚡ 5 Minutes to First Analysis

### 1. Installation

```bash
# Clone
git clone <repository-url>
cd a4p

# Install dependencies
pip install -r requirements.txt
```

### 2. Verify Installation

```bash
# Run tests
python -m pytest tests/ -v

# Run examples
python examples/basic_usage.py
```

### 3. First Document Analysis

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Base
from annex4parser.document_ingestion import ingest_document
from pathlib import Path

# Create database
engine = create_engine("sqlite:///compliance.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Analyze document
with Session() as session:
    doc_record = ingest_document(Path("your_document.pdf"), session)
    
    print(f"Document: {doc_record.filename}")
    print(f"Found matches: {len(doc_record.mappings)}")
    
    for mapping in doc_record.mappings:
        print(f"- {mapping.rule.section_code}: {mapping.confidence_score:.2f}")
```

## 🎯 Core Features

### ✅ What Works Right Now

- **Keyword Matching** - keyword search
- **Semantic Matching** - semantic analysis
- **Document Ingestion** - PDF/DOCX loading
- **Regulation Monitoring** - update monitoring
- **Database Storage** - result storage

### 📊 Analysis Results

```
Document: risk_assessment.pdf
Found matches: 4
- Article9.2: 0.85 (Risk Management)
- Article10.1: 0.72 (Data Governance)  
- Article15.3: 0.68 (Documentation)
- Article16.1: 0.45 (Accuracy & Security)
```

## 🔧 Customization for Your Needs

### Changing Thresholds

```python
# Stricter analysis
matches = semantic_match_rules(session, text, threshold=0.3)

# More lenient analysis  
matches = semantic_match_rules(session, text, threshold=0.05)
```

### Adding Your Own Rules

```python
from annex4parser.models import Regulation, Rule

# Create regulation
reg = Regulation(name="Custom Regulation", version="1.0")
session.add(reg)

# Add rules
rule = Rule(
    regulation_id=reg.id,
    section_code="Custom1",
    title="Custom Requirement",
    content="Your custom requirement text"
)
session.add(rule)
```

## 📁 Project Structure

```
a4p/
├── annex4parser/          # Main code
│   ├── mapper/           # Analyzers
│   ├── models.py         # Database models
│   └── document_ingestion.py
├── tests/                # Tests
├── examples/             # Examples
├── README.md            # Main documentation
├── DEPLOYMENT.md        # Deployment
└── requirements.txt     # Dependencies
```

## 🚨 Common Issues

### "Module not found"
```bash
# Make sure you're in the correct directory
cd a4p
pip install -r requirements.txt
```

### "No matches found"
```python
# Check that rules are loaded
rules = session.query(Rule).all()
print(f"Rules in database: {len(rules)}")

# Try lowering the threshold
matches = semantic_match_rules(session, text, threshold=0.05)
```

### "Database locked"
```python
# Close connections
session.close()
engine.dispose()
```

## 📈 Next Steps

1. **Study examples** in the `examples/` folder
2. **Set up production** according to `DEPLOYMENT.md`
3. **Add your own rules** to the database
4. **Integrate into your system** via API

## 🆘 Need Help?

- 📖 [Full Documentation](README.md)
- 🧪 [Code Examples](examples/README.md)
- 🚀 [Deployment](DEPLOYMENT.md)
- 🐛 [Create Issue](https://github.com/your-repo/issues)

---

**Ready to use!** 🎉
