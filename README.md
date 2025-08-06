# annex4parser

Utilities for parsing compliance documents and monitoring updates to the EU AI Act.

## Installation

```sh
pip install -r requirements.txt
```

## Running Tests

```sh
pytest -q
```

## Usage

### Update regulation text

Fetch the latest version of a regulation and store articles in a SQLite database:

```sh
python -m annex4parser --name "EU AI Act" --version 2024.12 --url https://example.com/ai-act.html
```

### Ingest a document

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser import document_ingestion, models

engine = create_engine("sqlite:///compliance.db")
models.Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
with Session() as session:
    document_ingestion.ingest_document(Path("risk_assessment.pdf"), session)
```

The document text is stored in the database and automatically mapped to matching AI Act rules.
