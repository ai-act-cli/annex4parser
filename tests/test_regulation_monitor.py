import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from annex4parser.models import Base, Document, DocumentRuleMapping, Regulation, Rule, ComplianceAlert
from annex4parser.regulation_monitor import update_regulation, canonicalize, parse_rules

def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" Article 6 (1) ", "Article6.1"),
        ("Article6(1)(i)", "Article6.1.i"),
        ("AnnexIV(2)a", "AnnexIV.2.a"),
        ("Annex IV (2) (a)", "AnnexIV.2.a"),
        ("Article10a(1)", "Article10a.1"),
        ("Article6..1", "Article6.1"),
        (".Article6.1.", "Article6.1"),
        ("", ""),
        (None, None),
        ("()", "()"),
        ("???", "???"),
    ],
)
def test_canonicalize(raw, expected):
    assert canonicalize(raw) == expected


def test_parse_rules_handles_lettered_article():
    text = "Article 10a Title\n1. First paragraph\n"
    parsed = parse_rules(text)
    codes = {r["section_code"] for r in parsed}
    assert "Article10a" in codes
    assert "Article10a.1" in codes


def test_parse_rules_strips_space_before_dash():
    text = "Article 1  — Scope\nBody\n"
    parsed = parse_rules(text)
    title = next(r["title"] for r in parsed if r["section_code"] == "Article1")
    assert title == "Scope"


def test_order_index_zero_padding():
    text = (
        "Article 5 Title\n"
        "1. First paragraph\n"
        "   (a) Alpha\n"
        "   (b) Beta\n"
        "   (C) Gamma\n"
        "10. Tenth paragraph\n"
        "   (a) Tenth Alpha\n"
    )
    parsed = parse_rules(text)
    r1 = next(r for r in parsed if r["section_code"] == "Article5.1")
    r10 = next(r for r in parsed if r["section_code"] == "Article5.10")
    r1a = next(r for r in parsed if r["section_code"] == "Article5.1.a")
    r1c = next(r for r in parsed if r["section_code"] == "Article5.1.c")
    assert r1["order_index"] == "001"
    assert r10["order_index"] == "010"
    assert r1a["order_index"] == "a"
    assert r1c["order_index"] == "c"

def test_update_regulation_creates_alerts(monkeypatch):
    session = setup_db()

    old_text = (
        "Article 9 Risk management\n1. Intro\n2. Old text.\n"
        "Article 10 Data governance\n1. Same text.\n"
    )
    new_text = (
        "Article 9 Risk management\n1. Intro\n2. Updated text.\n"
        "Article 10 Data governance\n1. Same text.\n"
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
    assert len(alerts) == 2
    types = {a.alert_type for a in alerts}
    assert "rule_updated" in types
    assert "document_outdated" in types
    rule_alert = next(a for a in alerts if a.alert_type == "rule_updated")
    doc_alert = next(a for a in alerts if a.alert_type == "document_outdated")
    new_rule = session.query(Rule).filter_by(section_code='Article9.2', version='2').first()
    assert rule_alert.rule_id == new_rule.id
    assert rule_alert.document_id == doc.id
    assert doc_alert.document_id == doc.id
    # document should be marked outdated
    assert session.get(Document, doc.id).compliance_status == 'outdated'
