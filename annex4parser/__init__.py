# annex4parser package
"""AI Compliance Document Parser - система для автоматического анализа документов на соответствие требованиям EU AI Act."""

from .models import (
    Regulation, Rule, Document, DocumentRuleMapping, ComplianceAlert,
    Source, RegulationSourceLog
)
from .regulation_monitor import RegulationMonitor, update_regulation
from .regulation_monitor_v2 import RegulationMonitorV2, update_all_regulations
from .document_ingestion import ingest_document
from .mapper.combined_mapper import combined_match_rules
from .legal_diff import LegalDiffAnalyzer, analyze_legal_changes, classify_change
from .alerts import AlertEmitter, emit_rule_changed, emit_rss_update, emit_regulation_update

__version__ = "2.0.0"
__author__ = "Annex4Parser Team"

__all__ = [
    # Models
    "Regulation", "Rule", "Document", "DocumentRuleMapping", "ComplianceAlert",
    "Source", "RegulationSourceLog",
    
    # Monitoring
    "RegulationMonitor", "update_regulation",
    "RegulationMonitorV2", "update_all_regulations",
    
    # Document processing
    "ingest_document", "combined_match_rules",
    
    # Legal analysis
    "LegalDiffAnalyzer", "analyze_legal_changes", "classify_change",
    
    # Alerts
    "AlertEmitter", "emit_rule_changed", "emit_rss_update", "emit_regulation_update",
]
