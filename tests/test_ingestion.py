import tempfile
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from annex4parser.document_ingestion import ingest_document
from annex4parser.models import Base, Regulation, Rule, DocumentRuleMapping
from annex4parser.mapper.mapper import DEFAULT_KEYWORD_MAP

import docx

def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def create_sample_docx(text: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc = docx.Document()
    doc.add_paragraph(text)
    doc.save(tmp.name)
    return Path(tmp.name)

def test_ingest_and_map_creates_mappings():
    session = setup_db()
    reg = Regulation(name='EU AI Act', celex_id='32024R1689', version='1')
    session.add(reg)
    session.flush()
    # Создаем правила из DEFAULT_KEYWORD_MAP
    for code in DEFAULT_KEYWORD_MAP.values():
        session.add(Rule(regulation_id=reg.id, section_code=code, title='', content=''))
    
    # Также создаем правила из YAML keywords
    from annex4parser.mapper.mapper import _get_keyword_map
    yaml_keywords = _get_keyword_map()
    for code in yaml_keywords.values():
        if code not in DEFAULT_KEYWORD_MAP.values():  # Не дублируем
            session.add(Rule(regulation_id=reg.id, section_code=code, title='', content=''))
    
    session.commit()

    doc_path = create_sample_docx('This document covers risk management and documentation requirements.')

    ingest_document(doc_path, session)

    mappings = session.query(DocumentRuleMapping).all()
    codes = {m.rule.section_code for m in mappings}
    assert 'Article9.2' in codes
    assert 'Article11' in codes or 'AnnexIV' in codes, f"Should find documentation mapping, got codes: {codes}"
