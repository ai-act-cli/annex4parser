# models.py
"""SQLAlchemy models for the compliance database.

This module defines ORM models corresponding to regulations, rules,
documents, mappings and compliance alerts.  The schema closely
follows the design outlined in the high‑level architecture for
tracking EU AI Act compliance, and includes helper utilities for
generating UUID primary keys.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
import uuid


Base = declarative_base()


def generate_uuid():
    """Generate UUID objects compatible with SQLAlchemy's UUID type."""
    return uuid.uuid4()


class Regulation(Base):
    __tablename__ = "regulations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    effective_date = Column(DateTime, nullable=True)
    source_url = Column(Text, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    status = Column(
        Enum("active", "draft", "superseded", name="regulation_status"), default="active"
    )
    rules = relationship("Rule", back_populates="regulation")


class Rule(Base):
    __tablename__ = "rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    regulation_id = Column(UUID(as_uuid=True), ForeignKey("regulations.id"))
    section_code = Column(String(50), nullable=False)
    title = Column(Text)
    content = Column(Text)
    risk_level = Column(
        Enum("critical", "high", "medium", "low", name="risk_level"), default="medium"
    )
    version = Column(String(50), default="1.0")
    parent_rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id"), nullable=True)
    effective_date = Column(DateTime, nullable=True)
    last_modified = Column(DateTime, default=datetime.utcnow)
    regulation = relationship("Regulation", back_populates="rules")


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    customer_id = Column(UUID(as_uuid=True))
    filename = Column(String(255))
    file_path = Column(Text)
    ai_system_name = Column(String(255))
    document_type = Column(
        Enum("risk_assessment", "training_data", "validation", "incident_log", name="doc_type")
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(DateTime, default=datetime.utcnow)
    compliance_status = Column(
        Enum("compliant", "outdated", "under_review", "non_compliant", name="compliance_status"),
        default="under_review",
    )
    storage_tier = Column(
        Enum("hot", "warm", "cold", name="storage_tier"), default="hot"
    )
    mappings = relationship("DocumentRuleMapping", back_populates="document")


class DocumentRuleMapping(Base):
    __tablename__ = "document_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id"))
    compliance_method = Column(Text)
    confidence_score = Column(Float, default=0.0)
    mapped_by = Column(
        Enum("auto", "manual", "ai_suggested", name="mapped_by"), default="ai_suggested"
    )
    mapped_at = Column(DateTime, default=datetime.utcnow)
    last_verified = Column(DateTime, default=datetime.utcnow)
    document = relationship("Document", back_populates="mappings")
    rule = relationship("Rule")


class ComplianceAlert(Base):
    __tablename__ = "compliance_alerts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id"))
    alert_type = Column(
        Enum("rule_updated", "document_outdated", "new_requirement", name="alert_type")
    )
    priority = Column(Enum("urgent", "high", "medium", "low", name="alert_priority"))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    assigned_to = Column(UUID(as_uuid=True), nullable=True)