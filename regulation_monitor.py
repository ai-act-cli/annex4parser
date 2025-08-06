# regulation_monitor.py
"""Monitor regulatory sources and update local rule records."""

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import (
    Regulation,
    Rule,
    DocumentRuleMapping,
    ComplianceAlert,
    Document,
)
from datetime import datetime
import re

def fetch_regulation_text(url: str) -> str:
    """Получить текст нормативного документа (HTML→текст)."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    return soup.get_text(separator="\n")

def parse_rules(raw_text: str) -> list[dict]:
    """Parse raw regulation text into individual rule entries.

    The parser looks for blocks starting with ``Article <code>`` and captures the
    optional title on the same line and the following content until the next
    article header.
    """
    rules: list[dict] = []
    # Split text on lines that start with "Article <number>"
    blocks = re.split(r"\n(?=Article\s+\d)", raw_text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        first_line = lines[0]
        m = re.match(r"Article\s+([\d\.\(\)a-zA-Z]+)\s*-?\s*(.*)", first_line)
        if not m:
            continue
        code = m.group(1).strip()
        title = m.group(2).strip()
        content = "\n".join(lines[1:]).strip()
        rules.append({
            "section_code": f"Article{code}",
            "title": title,
            "content": content,
        })
    return rules

def update_regulation(db: Session, name: str, version: str, url: str) -> Regulation:
    """Fetch the latest regulation text and update rules.

    If this version already exists in the database the function exits early.
    When a rule's content changes between versions, a ``ComplianceAlert`` is
    generated for each document mapped to the previous version of that rule and
    the document is marked as ``outdated``.
    """

    raw_text = fetch_regulation_text(url)
    # Abort if the regulation version is already stored
    if db.query(Regulation).filter_by(name=name, version=version).first():
        return db.query(Regulation).filter_by(name=name, version=version).first()

    previous_reg = (
        db.query(Regulation)
        .filter(Regulation.name == name)
        .order_by(Regulation.version.desc())
        .first()
    )

    reg = Regulation(
        name=name,
        version=version,
        source_url=url,
        effective_date=datetime.utcnow(),
        last_updated=datetime.utcnow(),
        status="active",
    )
    db.add(reg)
    db.flush()  # obtain id for FK relations

    for rule_data in parse_rules(raw_text):
        new_rule = Rule(
            regulation_id=reg.id,
            section_code=rule_data["section_code"],
            title=rule_data["title"],
            content=rule_data["content"],
            risk_level="medium",
            version=version,
            effective_date=datetime.utcnow(),
            last_modified=datetime.utcnow(),
        )
        db.add(new_rule)

        if previous_reg:
            old_rule = (
                db.query(Rule)
                .filter_by(regulation_id=previous_reg.id, section_code=rule_data["section_code"])
                .first()
            )
            if old_rule and old_rule.content.strip() != rule_data["content"].strip():
                old_len = len(old_rule.content or "")
                new_len = len(rule_data["content"] or "")
                severity = "major" if abs(new_len - old_len) / max(old_len, 1) > 0.1 else "minor"
                mappings = db.query(DocumentRuleMapping).filter_by(rule_id=old_rule.id).all()
                for mapping in mappings:
                    priority = (
                        "high" if severity == "major" or old_rule.risk_level in {"critical", "high"} else "medium"
                    )
                    alert = ComplianceAlert(
                        document_id=mapping.document_id,
                        rule_id=new_rule.id,
                        alert_type="rule_updated",
                        priority=priority,
                        message=f"{rule_data['section_code']} updated",
                    )
                    db.add(alert)
                    # mark document as outdated
                    doc = db.query(Document).get(mapping.document_id)
                    if doc:
                        doc.compliance_status = "outdated"

    db.commit()
    return reg
