import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from annex4parser.models import Base, Document, DocumentRuleMapping, Regulation, Rule, ComplianceAlert
from annex4parser.regulation_monitor import update_regulation

def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_update_regulation_creates_alerts(monkeypatch):
    session = setup_db()

    old_text = (
        "Article 9.2 Risk management\nOld text.\n"
        "Article 10.1 Data governance\nSame text.\n"
    )
    new_text = (
        "Article 9.2 Risk management\nUpdated text.\n"
        "Article 10.1 Data governance\nSame text.\n"
    )

    # first version
    monkeypatch.setattr('annex4parser.regulation_monitor.fetch_regulation_text', lambda url: old_text)
    update_regulation(session, 'EU AI Act', '1', 'http://example.com')

    # create document mapped to Article9.2
    rule_v1 = session.query(Rule).filter_by(section_code='Article9.2').first()
    doc = Document(filename='doc.docx', file_path='doc.docx', ai_system_name='sys', document_type='risk_assessment')
    session.add(doc)
    session.flush()
    session.add(DocumentRuleMapping(document_id=doc.id, rule_id=rule_v1.id))
    session.commit()

    # new version with updated article 9.2
    monkeypatch.setattr('annex4parser.regulation_monitor.fetch_regulation_text', lambda url: new_text)
    update_regulation(session, 'EU AI Act', '2', 'http://example.com')

    alerts = session.query(ComplianceAlert).all()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.document_id == doc.id
    new_rule = session.query(Rule).filter_by(section_code='Article9.2', version='2').first()
    assert alert.rule_id == new_rule.id
    # document should be marked outdated
    assert session.get(Document, doc.id).compliance_status == 'outdated'
