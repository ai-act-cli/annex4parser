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
    """Split a regulation text into individual rule entries.

    The parser searches for lines beginning with "Article " and
    captures the code and optional title.  It returns a list of
    dictionaries containing the ``section_code``, ``title`` and
    ``content`` of each article.  For example, if the raw text
    contains ``Article 15.3  Documentation requirements`` the
    returned ``section_code`` will be ``"Article15.3"``.
    """
    rules: List[dict] = []
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
    def update(self, name: str, version: str, url: str) -> Regulation:
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
        existing = self.db.query(Regulation).filter_by(name=name, version=version).first()
        if existing:
            return existing

        # Fetch current text, using cache to avoid redundant downloads
        cached = self.get_cached_text(url)
        raw_text = fetch_regulation_text(url)
        if cached is not None and cached.strip() == raw_text.strip():
            logger.info("No substantive changes detected for %s; skipping update.", name)
            return existing if existing else Regulation(name=name, version=version)
        # Save the new content in cache for next run
        self.save_cached_text(url, raw_text)

        # Retrieve the most recent previous version (if any)
        previous_reg = (
            self.db.query(Regulation)
            .filter(Regulation.name == name)
            .order_by(Regulation.version.desc())
            .first()
        )

        # Create new regulation record
        reg = Regulation(
            name=name,
            version=version,
            source_url=url,
            effective_date=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            status="active",
        )
        self.db.add(reg)
        self.db.flush()  # get ID for FK relations

        # Parse and insert new rules
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
            self.db.add(new_rule)

            # Compare against previous version of the same section
            if previous_reg:
                old_rule = (
                    self.db.query(Rule)
                    .filter_by(regulation_id=previous_reg.id, section_code=rule_data["section_code"])
                    .first()
                )
                if old_rule and old_rule.content.strip() != rule_data["content"].strip():
                    # Compute a unified diff between the old and new content
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
                        # mark document as outdated
                        doc = self.db.get(Document, mapping.document_id)
                        if doc:
                            doc.compliance_status = "outdated"

        self.db.commit()
        return reg


# Legacy helper for backward compatibility
_default_monitor: Optional[RegulationMonitor] = None


def update_regulation(db: Session, name: str, version: str, url: str) -> Regulation:
    """Backward compatible wrapper around :meth:`RegulationMonitor.update`.

    This function will lazily instantiate a :class:`RegulationMonitor`
    bound to the provided session and delegate to its ``update`` method.
    It retains the original signature of the ``update_regulation``
    function to ease migration from older versions of the library.
    """
    global _default_monitor
    if _default_monitor is None or _default_monitor.db is not db:
        _default_monitor = RegulationMonitor(db)
    return _default_monitor.update(name=name, version=version, url=url)
