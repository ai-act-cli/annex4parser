"""Semantic-based mapping between document text and AI Act articles.

This module provides a simple implementation for matching compliance
documents to specific sections of the EU AI Act based on semantic
similarity. It uses TF‑IDF vectorization from scikit‑learn to
represent both the document text and the rule contents and then
computes cosine similarity between them. Rules with similarity
scores above a configurable threshold are considered relevant and
returned along with their confidence score.

The intent of this module is to augment the basic keyword matching
defined in :mod:`annex4parser.mapper` with a more flexible
similarity measure. When combined, these approaches can improve
recall and precision of rule mappings.
"""

from __future__ import annotations

from typing import Dict, Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sqlalchemy.orm import Session

from ..models import Rule


def semantic_match_rules(
    db: Session, doc_text: str, *, threshold: float = 0.1
) -> Dict[str, float]:
    """Compute semantic similarity between a document and all rules.

    Parameters
    ----------
    db : Session
        SQLAlchemy session used to fetch rules from the database.
    doc_text : str
        The text of the document to be mapped.
    threshold : float, optional
        Minimum cosine similarity score required for a rule to be
        included in the result. Defaults to 0.1.

    Returns
    -------
    Dict[str, float]
        A mapping of rule section codes to similarity scores. Only
        rules whose content exceeds the given threshold are returned.

    Notes
    -----
    This function performs a per‑document calculation of TF‑IDF
    vectors. For a small number of rules this is efficient, but if
    the corpus grows significantly consider caching rule vectors or
    reusing the fitted vectorizer across documents.
    """
    # Retrieve all rules from the database. Use a list here so that
    # indices remain stable relative to the computed similarity array.
    rules: Iterable[Rule] = list(db.query(Rule).all())
    if not rules or not doc_text.strip():
        return {}

    # Build a corpus consisting of the document text followed by each
    # rule's content. Null or empty rule content is safely handled.
    corpus = [doc_text]
    for rule in rules:
        corpus.append(rule.content or "")

    # Fit a TF‑IDF vectorizer on the combined corpus. English stop
    # words are removed to reduce noise. Lowercasing is implicit.
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # The first vector corresponds to the document; subsequent
    # vectors correspond to the rules in the same order as in
    # ``rules``. Compute cosine similarity between the document and
    # each rule.
    doc_vector = tfidf_matrix[0:1]
    rule_vectors = tfidf_matrix[1:]
    cosine_sim = linear_kernel(doc_vector, rule_vectors).flatten()

    # Assemble a mapping of section codes to similarity scores
    result: Dict[str, float] = {}
    for rule, score in zip(rules, cosine_sim):
        if score >= threshold:
            # Use section_code as the key so that downstream callers
            # can resolve the rule easily.
            result[rule.section_code] = float(score)
    return result
