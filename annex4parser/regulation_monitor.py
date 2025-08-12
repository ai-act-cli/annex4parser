# regulation_monitor.py
"""Monitor regulatory sources and update local rule records.

This module provides utilities for fetching the latest version of a
regulatory document (such as the EU AI Act), parsing it into
individual articles, comparing it against previously stored
versions, and updating a relational database accordingly.  It
extends the original implementation with support for local
caching of fetched content, unified diffs for precise change
classification, and a simple severity estimator.

The primary entry point is the :class:`RegulationMonitor`, which
encapsulates a SQLAlchemy session and optional cache directory.
Applications should instantiate this class once and call
``update`` whenever a new version of a regulation needs to be
processed.  For compatibility with existing code, the
module-level ``update_regulation`` function delegates to the
corresponding method on an internal monitor instance.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

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

logger = logging.getLogger(__name__)


def canonicalize(code: str) -> str:
    """Normalize section codes by removing spaces and unifying delimiters."""
    if not code:
        return code
    code = re.sub(r"\s+", "", code)
    # convert parenthetical markers like "(1)" into dotted notation and
    # ensure a trailing dot to separate any following tokens
    code = re.sub(r"\(([^)]+)\)", r".\1.", code)
    code = re.sub(r"\.{2,}", ".", code)
    return code.strip(".")


def fetch_regulation_text(url: str) -> str:
    """Download a regulation from the given URL and return its plain text.

    The page is retrieved via ``requests`` and parsed using
    ``BeautifulSoup``.  All HTML tags are stripped and newlines are
    preserved to aid subsequent rule parsing.
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    return soup.get_text(separator="\n")


def parse_rules(raw_text: str) -> List[dict]:
    """Parse Articles and Annexes into rule entries (with optional parents).

    The ``section_code`` follows a dotted grammar to reflect the legal
    hierarchy:

    ``ArticleN[.n][.letter][.roman]…`` (e.g. ``Article10a.1.b.i``)
    ``AnnexIV[.n][.letter]…`` (e.g. ``AnnexIV.2.a``)

    Returns list of dicts with:
      - section_code: e.g. "Article11", "AnnexIV", "AnnexIV.1", "AnnexIV.1.a"
      - title: optional heading
      - content: text body for the node
      - parent_section_code: optional (for Annex children)
    """
    rules: List[dict] = []
    text = raw_text.strip()

    # ---- Сначала найдем все границы Articles и Annexes ----
    boundaries = []
    
    # Находим все Articles
    for match in re.finditer(r"(?im)^(\s*Article\s+\d+[a-z]?\b)", text):
        boundaries.append(("Article", match.start(), match.group(1).strip()))
    
    # Находим все Annexes (case insensitive)
    for match in re.finditer(r"(?i)(?m)^(\s*ANNEX\s+[IVXLC]+\b)", text):
        boundaries.append(("Annex", match.start(), match.group(1).strip()))
    
    # Сортируем по позиции в тексте
    boundaries.sort(key=lambda x: x[1])
    
    # ---- Обрабатываем каждый блок ----
    for i, (block_type, start_pos, header) in enumerate(boundaries):
        # Определяем конец блока
        end_pos = boundaries[i + 1][1] if i + 1 < len(boundaries) else len(text)
        block_text = text[start_pos:end_pos].strip()
        
        if block_type == "Article":
            # Парсим Article
            lines = block_text.splitlines()
            m = re.match(r"\s*Article\s+(\d+[a-z]?)\b(.*)", lines[0], re.I)
            if m:
                code = m.group(1).strip()
                rest = m.group(2) or ""
                title = re.sub(r"^[–—-]\s*", "", rest).strip()
                title_line_idx = 0
                if not title:
                    k = 1
                    while k < min(4, len(lines)):
                        cand = lines[k].strip()
                        if cand and not re.match(r"^\d+\.\s+", cand) and not re.match(r"^(ANNEX|Article)\b", cand, re.I):
                            title = cand
                            title_line_idx = k
                            break
                        k += 1
                if not title:
                    buff = []
                    for ln in lines[1:7]:
                        s = ln.strip()
                        if not s or re.match(r"^\d+\.\s+", s) or re.match(r"^(ANNEX|Article)\b", s, re.I):
                            break
                        buff.append(s)
                    if buff:
                        title = " ".join(buff).split(" – ")[0].split(" — ")[0].strip()
                        title_line_idx = len(buff)
                raw = "\n".join(lines[title_line_idx+1:]).strip()
                content = re.sub(r"\n{3,}", "\n\n", raw)
                parent_code = canonicalize(f"Article{code}")
                rules.append({
                    "section_code": parent_code,
                    "title": title,
                    "content": content,
                })
                _parse_article_subsections(rules, parent_code, content)
        
        elif block_type == "Annex":
            # Парсим Annex
            lines = block_text.splitlines()
            header_line = lines[0]
            m = re.match(r"(?i)\s*ANNEX\s+([IVXLC]+)\b(.*)", header_line)
            if m:
                roman = m.group(1).upper()
                annex_title = re.sub(r"^[–—-]\s*", "", (m.group(2) or "").strip())
                consumed = 0
                if not annex_title:
                    buff = []
                    for ln in lines[1:7]:
                        s = ln.strip()
                        if not s or re.match(r"^\d+\.\s+", s):
                            break
                        buff.append(s)
                    if buff:
                        annex_title = " ".join(buff).strip()
                        consumed = len(buff)
                raw_body = "\n".join(lines[1+consumed:]).strip()
                body = re.sub(r"\n{3,}", "\n\n", raw_body)

                parent_code = canonicalize(f"Annex{roman}")
                rules.append({
                    "section_code": parent_code,
                    "title": annex_title,
                    "content": body,
                })

                # Внутри Annex парсим подразделы
                _parse_annex_subsections(rules, parent_code, body)

    return rules


def _parse_article_subsections(rules: List[dict], parent_code: str, body: str):
    """Парсит пункты и подпункты внутри Article."""
    top_parts = re.split(r"(?m)^\s*(\d+)\.\s+", body)
    if len(top_parts) >= 3:
        for i in range(1, len(top_parts), 2):
            num = top_parts[i]
            text_i = top_parts[i + 1] if i + 1 < len(top_parts) else ""
            code_i = canonicalize(f"{parent_code}.{num}")
            rules.append({
                "section_code": code_i,
                "title": "",
                "content": text_i.strip(),
                "parent_section_code": canonicalize(parent_code),
            })
            sub_parts = re.split(r"(?m)^\s*\(([a-z])\)\s+", text_i)
            if len(sub_parts) >= 3:
                for j in range(1, len(sub_parts), 2):
                    letter = sub_parts[j]
                    text_j = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
                    sub_code = canonicalize(f"{code_i}.{letter}")
                    rules.append({
                        "section_code": sub_code,
                        "title": "",
                        "content": text_j.strip(),
                        "parent_section_code": code_i,
                    })


def _parse_annex_subsections(rules: List[dict], parent_code: str, body: str):
    """Парсит подразделы внутри Annex."""
    # Разрежем по верхнему уровню "N." (в начале строки)
    top_parts = re.split(r"(?m)^\s*(\d+)\.\s+", body)
    # split даёт: ["intro", "1", "text1", "2", "text2", ...]
    if len(top_parts) >= 3:
        for i in range(1, len(top_parts), 2):
            num = top_parts[i]
            text_i = top_parts[i+1] if i+1 < len(top_parts) else ""
            code_i = canonicalize(f"{parent_code}.{num}")
            # Добавляем узел 1-го уровня
            rules.append({
                "section_code": code_i,
                "title": "",
                "content": text_i.strip(),
                "parent_section_code": canonicalize(parent_code),
            })
            # Разрезаем подпункты (a), (b) ...
            sub_parts = re.split(r"(?m)^\s*\(([a-z])\)\s+", text_i)
            if len(sub_parts) >= 3:
                # ["prefix", "a", "text_a", "b", "text_b", ...]
                for j in range(1, len(sub_parts), 2):
                    letter = sub_parts[j]
                    text_j = sub_parts[j+1] if j+1 < len(sub_parts) else ""
                    sub_code = canonicalize(f"{code_i}.{letter}")
                    rules.append({
                        "section_code": sub_code,
                        "title": "",
                        "content": text_j.strip(),
                        "parent_section_code": code_i,
                    })


class RegulationMonitor:
    """A helper class for processing regulation updates.

    Parameters
    ----------
    db : Session
        A SQLAlchemy session connected to the compliance database.
    cache_dir : str or Path, optional
        Directory for storing cached regulation texts.  When
        provided, previously downloaded content will be saved and
        reused to avoid unnecessary network requests.  Defaults to
        ``~/.annex4parser/cache``.
    """

    def __init__(self, db: Session, cache_dir: Optional[Path] = None) -> None:
        self.db = db
        if cache_dir is None:
            home = Path.home()
            cache_dir = home / ".annex4parser" / "cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cache utilities
    # ------------------------------------------------------------------
    def _slugify(self, url: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", url).strip("_")

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{self._slugify(url)}.txt"

    def get_cached_text(self, url: str) -> Optional[str]:
        path = self._cache_path(url)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.debug("Failed to read cached version for %s: %s", url, exc)
        return None

    def save_cached_text(self, url: str, text: str) -> None:
        path = self._cache_path(url)
        try:
            path.write_text(text, encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to save cached version for %s: %s", url, exc)

    # ------------------------------------------------------------------
    # Diff utilities
    # ------------------------------------------------------------------
    @staticmethod
    def compute_diff(old: str, new: str) -> str:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, lineterm="")
        return "".join(diff)

    @staticmethod
    def classify_change(diff: str) -> str:
        """Classify a change as major, minor or clarification.

        The heuristic is based on the number of added or removed
        characters in the unified diff.  Adjust the thresholds as
        needed for your compliance requirements.
        """
        added = sum(len(line) for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        removed = sum(len(line) for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        total = added + removed
        if total > 500:
            return "major"
        if total > 100:
            return "minor"
        return "clarification"

    # ------------------------------------------------------------------
    # Main update routine
    # ------------------------------------------------------------------
    def update(self, name: str, version: str, url: str, celex_id: str = "UNKNOWN") -> Regulation:
        """Fetch a new version of a regulation and update the database.

        This method wraps the legacy :func:`update_regulation` logic with
        local caching and change classification.  It will skip
        processing if the downloaded text has not changed since the
        last invocation.

        Parameters
        ----------
        name : str
            The name of the regulation, e.g., "EU AI Act".
        version : str
            A version identifier supplied by the caller.  If a record
            with the same name and version already exists the method
            returns immediately.
        url : str
            URL from which to fetch the regulation text.
        """
        # Return existing record if version already loaded
        existing = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id, version=version)
            .first()
        )
        if existing:
            return existing

        # Fetch current text, using cache to avoid redundant downloads
        cached = self.get_cached_text(url)
        raw_text = fetch_regulation_text(url)
        if cached is not None and cached.strip() == raw_text.strip():
            logger.info("No substantive changes detected for %s; skipping update.", name)
            return existing if existing else Regulation(name=name, celex_id=celex_id, version=version)
        # Save the new content in cache for next run
        self.save_cached_text(url, raw_text)

        # Retrieve the most recent previous version (if any)
        previous_reg = (
            self.db.query(Regulation)
            .filter(Regulation.celex_id == celex_id)
            .order_by(Regulation.version.desc())
            .first()
        )

        # Create new regulation record
        reg = Regulation(
            name=name,
            celex_id=celex_id,
            version=version,
            source_url=url,
            effective_date=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            status="active",
        )
        self.db.add(reg)
        self.db.flush()  # get ID for FK relations

        # Парсим и вставляем новые правила (с поддержкой parent_rule_id для Annex)
        code_to_rule = {}
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
            parent_code = rule_data.get("parent_section_code")
            if parent_code:
                parent = code_to_rule.get(parent_code) or (
                    self.db.query(Rule)
                    .filter_by(regulation_id=reg.id, section_code=parent_code)
                    .first()
                )
                if parent:
                    new_rule.parent_rule_id = parent.id
            self.db.add(new_rule)
            self.db.flush()
            code_to_rule[new_rule.section_code] = new_rule

            # Сравниваем с предыдущей версией той же секции
            if previous_reg:
                old_rule = (
                    self.db.query(Rule)
                    .filter_by(regulation_id=previous_reg.id, section_code=rule_data["section_code"])
                    .first()
                )
                if old_rule and old_rule.content.strip() != rule_data["content"].strip():
                    # Вычисляем diff между старым и новым содержимым
                    diff = self.compute_diff(old_rule.content or "", rule_data["content"] or "")
                    severity = self.classify_change(diff)
                    mappings = self.db.query(DocumentRuleMapping).filter_by(rule_id=old_rule.id).all()
                    for mapping in mappings:
                        priority = (
                            "high"
                            if severity == "major" or old_rule.risk_level in {"critical", "high"}
                            else "medium"
                        )
                        alert = ComplianceAlert(
                            document_id=mapping.document_id,
                            rule_id=new_rule.id,
                            alert_type="rule_updated",
                            priority=priority,
                            message=f"{rule_data['section_code']} updated ({severity} change)",
                        )
                        self.db.add(alert)
                        # помечаем документ как устаревший
                        doc = self.db.get(Document, mapping.document_id)
                        if doc:
                            doc.compliance_status = "outdated"
                            doc.last_modified = datetime.utcnow()
                            doc_alert = ComplianceAlert(
                                document_id=doc.id,
                                rule_id=new_rule.id,
                                alert_type="document_outdated",
                                priority="high",
                                message=f"Document {doc.filename or doc.id} outdated due to changes in {rule_data['section_code']}",
                            )
                            self.db.add(doc_alert)

        self.db.commit()
        return reg


# Legacy helper for backward compatibility
_default_monitor: Optional[RegulationMonitor] = None


def update_regulation(db: Session, name: str, version: str, url: str, celex_id: str = "UNKNOWN") -> Regulation:
    """Backward compatible wrapper around :meth:`RegulationMonitor.update`.

    This function will lazily instantiate a :class:`RegulationMonitor`
    bound to the provided session and delegate to its ``update`` method.
    It retains the original signature of the ``update_regulation``
    function to ease migration from older versions of the library.
    """
    global _default_monitor
    if _default_monitor is None or _default_monitor.db is not db:
        _default_monitor = RegulationMonitor(db)
    return _default_monitor.update(name=name, version=version, url=url, celex_id=celex_id)
