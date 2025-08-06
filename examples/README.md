# Annex4Parser Usage Examples

This folder contains examples of using the Annex4Parser system for analyzing document compliance with EU AI Act requirements.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Make sure you're in the project root directory
cd a4p

# Activate virtual environment (if using)
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Basic Examples

```bash
# Run all examples
python examples/basic_usage.py
```

## 📁 Examples Structure

### `basic_usage.py`
Basic system usage examples:

- **Database Setup** - creating test database with rules
- **Keyword Matching** - keyword search
- **Semantic Matching** - semantic analysis
- **Combined Matching** - combined analysis
- **Document Ingestion** - document loading and analysis
- **Regulation Monitoring** - monitoring updates

## 🧪 Testing Examples

### Run with Detailed Output

```bash
python examples/basic_usage.py
```

Expected output:
```
🚀 Annex4Parser - Usage Examples
==================================================
🔧 Setting up database...
✅ Created 4 rules

🔍 Keyword search example:

Text 1: Our AI system implements comprehensive risk manage...
Found matches: {'Article9.2': 0.8}

Text 2: The system uses high-quality training data with pr...
Found matches: {'Article10.1': 0.8}

Text 3: We maintain detailed documentation for all AI oper...
Found matches: {'Article15.3': 0.8}

🧠 Semantic analysis example:
Text: Our organization has implemented comprehensive risk assessment procedures for AI systems.
Semantic matches: {'Article9.2': 0.25}

⚡ Combined analysis example:
Text: Our AI system implements risk management and maintains proper documentation.
Combined matches: {'Article9.2': 0.65, 'Article15.3': 0.42}

📄 Document ingestion example:
Document: tmp_xxxxx.docx
Found matches: 3
  - Article9.2: 0.45
  - Article15.3: 0.42
  - Article10.1: 0.43

📊 Regulation monitoring example:
✓ Monitoring created
✓ Update method: True
✓ Compute_diff method: True
✓ Diff utilities working (change type: minor)

✅ All examples completed successfully!
```

## 🔧 Development Setup

### Creating Your Own Examples

1. Create a new file in the `examples/` folder
2. Import necessary modules:

```python
import sys
import os
from pathlib import Path

# Add root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from annex4parser.models import *
from annex4parser.mapper.mapper import match_rules
from annex4parser.document_ingestion import ingest_document
```

3. Use the existing `setup_database()` function or create your own

### Example of Creating Your Own Analyzer

```python
def custom_analysis(session, document_path):
    """Custom document analysis"""
    
    # Load document
    doc_record = ingest_document(Path(document_path), session)
    
    # Analyze compliance
    high_risk_mappings = [
        m for m in doc_record.mappings 
        if m.rule.risk_level == 'high' and m.confidence_score > 0.7
    ]
    
    print(f"Found high-risk matches: {len(high_risk_mappings)}")
    
    for mapping in high_risk_mappings:
        print(f"⚠️ {mapping.rule.section_code}: {mapping.confidence_score:.2f}")
    
    return high_risk_mappings
```

## 🚨 Troubleshooting

### Error: "Module not found"
```bash
# Make sure you're in the correct directory
cd a4p
python examples/basic_usage.py
```

### Error: "Database locked"
```python
# Close all connections
session.close()
engine.dispose()
```

### Error: "No rules found"
```python
# Check that rules are loaded
rules = session.query(Rule).all()
print(f"Rules in database: {len(rules)}")
```

## 📊 Results Analysis

### Interpreting Confidence Scores

- **0.8-1.0**: High compliance
- **0.5-0.8**: Medium compliance  
- **0.2-0.5**: Low compliance
- **0.0-0.2**: Minimal compliance

### Types of Matches

- **Keyword Matching**: Exact keyword match
- **Semantic Matching**: Semantic similarity
- **Combined Matching**: Combined analysis

## 🔄 Integration with Your Projects

### Copying Code

```python
# Copy needed functions from examples/basic_usage.py
def setup_database():
    # ... database setup code

def analyze_document(session, file_path):
    # ... document analysis code
```

### Adapting to Your Needs

```python
# Change thresholds for your requirements
matches = semantic_match_rules(session, text, threshold=0.3)  # Stricter

# Add your own rules
custom_rules = [
    {'section_code': 'Custom1', 'keywords': ['custom', 'requirement']}
]
```

## 📞 Support

- Create an Issue for example problems
- Check main documentation in `README.md`
- Study tests in the `tests/` folder

---

**Examples ready to use!** 🚀
