# annex4parser/combined_mapper.py
from __future__ import annotations
from typing import Dict
from sqlalchemy.orm import Session

from .mapper import match_rules          # keywords
from .semantic_mapper import semantic_match_rules  # TF-IDF + cosine
# from sentence_transformers import SentenceTransformer, util  # optional but heavy BERT

KW_WEIGHT   = 0.30
SEM_WEIGHT  = 0.70      # TF-IDF or BERT; total 1.0

def combined_match_rules(
    db: Session,
    doc_text: str,
    *,
    tfidf_threshold: float = 0.05,
) -> Dict[str, float]:
    """Mix keyword and semantic signals into a single score 0..1."""
    kw_hits  = match_rules(doc_text)                # {code: 0.8}
    sem_hits = semantic_match_rules(db, doc_text, threshold=tfidf_threshold)

    # --- Optionally replace TF-IDF with Sentence-BERT ---
    # model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    # doc_emb = model.encode(doc_text, normalize_embeddings=True)
    # sem_hits = {}
    # for rule in db.query(Rule).all():
    #     rule_emb = model.encode(rule.content or "", normalize_embeddings=True)
    #     score = util.cos_sim(doc_emb, rule_emb).item()
    #     if score >= tfidf_threshold:
    #         sem_hits[rule.section_code] = score
    # ----------------------------------------------------

    result: Dict[str, float] = {}
    codes = set(kw_hits) | set(sem_hits)

    for code in codes:
        kw_flag = 1.0 if code in kw_hits else 0.0
        sem_val = sem_hits.get(code, 0.0)

        score = KW_WEIGHT * kw_flag + SEM_WEIGHT * sem_val
        result[code] = min(score, 1.0)              # safety-clip

    return result