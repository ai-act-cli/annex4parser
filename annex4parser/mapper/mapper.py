# mapper.py
"""Keyword-based mapping between document text and AI Act articles.

This module defines a minimal prototype for mapping compliance
documents to specific sections of the EU AI Act based on simple
keyword matching.  The :func:`match_rules` function scans a
document's text for known phrases and returns a mapping of
``section_code`` → confidence score.  It is intended as a
starting point and can be replaced with more sophisticated NLP
techniques in the future.
"""

import re
from collections import defaultdict

# Simple keyword matrix → article code
KEYWORD_MAP = {
    # Risk Management
    "risk management": "Article9.2",
    "risk assessment": "Article9.2",
    "risk analysis": "Article9.2",
    "foreseeable risks": "Article9.2",
    
    # Data Governance
    "data governance": "Article10.1",
    "training data": "Article10.1",
    "data sets": "Article10.1",
    "data quality": "Article10.1",
    "representative data": "Article10.1",
    "statistical properties": "Article10.1",
    
    # Documentation
    "documentation": "Article15.3",
    "technical documentation": "Article15.3",
    "compliance documentation": "Article15.3",
    
    # Record Keeping
    "record keeping": "Article15.4",
    "logs": "Article15.4",
    "audit trail": "Article15.4",
    "system logs": "Article15.4",
    
    # Accuracy and Cybersecurity
    "accuracy": "Article16.1",
    "robustness": "Article16.1",
    "cybersecurity": "Article16.1",
    "accuracy metrics": "Article16.1",
    
    # Human Oversight
    "human oversight": "Article17.1",
    "human machine interface": "Article17.1",
    "human control": "Article17.1",
}


def match_rules(doc_text: str) -> dict[str, float]:
    """
    Search for keywords in a document and return a mapping from
    section codes to confidence scores.

    For each entry in :data:`KEYWORD_MAP`, the function performs a
    case‑insensitive whole‑word search.  When a keyword is found,
    the corresponding section code is added to the result with a
    fixed confidence of 0.8.  If a keyword appears multiple
    times, the highest confidence is retained.
    """
    result = defaultdict(float)
    for keyword, rule_code in KEYWORD_MAP.items():
        if re.search(rf"\b{re.escape(keyword)}\b", doc_text, re.IGNORECASE):
            result[rule_code] = max(result[rule_code], 0.8)
    return result
