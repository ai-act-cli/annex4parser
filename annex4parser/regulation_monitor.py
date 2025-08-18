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
import unicodedata
import hashlib
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

logger = logging.getLogger(__name__)

# Короткие стоп-слова — строка точно не title
STOP_START = re.compile(r"^(and|or|for|where|when|which|that)\b", re.I)
# «это уже текст, а не заголовок» — типичные глаголы в правовых пунктах
TITLE_VERB = re.compile(
    r"\b(shall|must|may|should|contain|contains|include|includes|apply|applies|"
    r"provide|provided|ensure|indicate|keep|draw up|affix|comply|take|inform|act|"
    r"establish|implement)\b",
    re.I,
)
# мусорные «бэктики» на EUR-Lex (например, Subject matter`)
BAD_TICKS = re.compile(r"[`´]")
# заголовки разделов — их не считаем title статьи
BAD_HEAD = re.compile(r"^(CHAPTER|SECTION|SUBSECTION|TITLE|ANNEX|PART)\b", re.I)
# Границы статей: не принимать кросс-ссылки типа "Article 98(2)"
ARTICLE_BOUNDARY_RE = re.compile(r"(?im)^\s*Article\s+\d+[a-zA-Z]?(?!\s*\()", re.I | re.M)
# Структурные заголовки (глава/секция/часть), которые выступают как «разделители» между статьями
STRUCT_BOUNDARY_RE = re.compile(
    r"(?im)^\s*(CHAPTER|SECTION|SUBSECTION|TITLE|PART)\s+[IVXLC0-9A-Z]+\b"
)
END_PUNCT = re.compile(r"[.:;]\s*$")
ALL_CAPS_ROMAN = re.compile(r"^[A-Z0-9\s\-–—IVXLC]+$")
ENUM_PREFIX = re.compile(r"^(\(?[0-9ivx]+\)?\.?|\([a-zA-Z]\))\s+")


def _is_title_like(s: str) -> bool:
    return (
        bool(s)
        and not s.startswith(("(", "["))
        and not STOP_START.match(s)
        and not s[:1].islower()
        and not TITLE_VERB.search(s)
        and not BAD_HEAD.match(s)
    )


def _clean_title_piece(s: str) -> str:
    return BAD_TICKS.sub("", s).strip()


def _clip_bilingual_trail(s: str) -> str:
    """
    Обрезать при склейке двух языков без разделителя.
    Пример: 'Committee procedureAusschussverfahren' -> 'Committee procedure'
    Эвристика: граница [a-z][A-Z][a-z]
    """
    return re.sub(r"(?<=[a-z])([A-Z][a-z].*)$", "", s).strip()


def _norm_title_text(s: str) -> str:
    s = BAD_TICKS.sub("", s)
    s = re.sub(r"^[\u2013\u2014\-:;,\.]+\s*", "", s).strip()
    s = _clip_bilingual_trail(s)
    s = re.split(r"\s{2,}", s)[0].strip()
    return s


def _is_hard_title_candidate(s: str) -> bool:
    """Более строгая проверка заголовка, чтобы безопасно искать его даже после начала пунктов."""
    return (
        _is_title_like(s)
        and not END_PUNCT.search(s)
        and not ALL_CAPS_ROMAN.fullmatch(s)
        and len(s) <= 220
    )


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


def format_order_index(idx: str) -> str:
    """Return a zero-padded string for numeric indices and lower-case letters."""
    if idx is None:
        return idx
    idx = str(idx)
    if idx.isdigit():
        return f"{int(idx):03d}"
    return idx.lower()


def _unwrap_soft_linebreaks(s: str) -> str:
    """Join soft-wrapped lines while keeping structural breaks intact."""
    s = re.sub(r"(\w)[\u2010-\u2014-]\s*\n\s*(\w)", r"\1\2", s)

    def _join(m: re.Match) -> str:
        before, after = m.group(1), m.group(2)
        if re.match(r"^\s*(?:\(?[a-z]\)|\([ivx]+\)|\d+\.)\s+", after, re.I):
            return before + "\n" + after
        if re.match(r"^(?:ANNEX|Article|Section|Chapter|Part)\b", after, re.I):
            return before + "\n" + after
        return before + " " + after

    return re.sub(r"([^\n])\n(?!\n)([^\n][^\n]*)", _join, s)


def _sanitize_content(text: str) -> str:
    """Remove stray footnote markers and collapse whitespace."""
    if not text:
        return ""
    raw_lines = text.splitlines()
    lines = []
    i = 0
    while i < len(raw_lines):
        ln = raw_lines[i]
        s = unicodedata.normalize("NFKC", ln).replace("\xa0", " ").strip()

        # Удаляем мусор, мешающий заголовкам на двуязычных страницах EUR-Lex
        # 1) дубли «ANNEXE IV», «ANNEXE XI», и т.п.
        s = re.sub(r"(?i)\bANNEXE\s+[IVXLC]+\b", "", s).strip()
        # 2) одиночные ISO-коды языка в колонке (EN, FR, PL …)
        if re.match(r"^[A-Z]{2,3}$", s):
            i += 1
            continue
        # 3) лишние бэктики/острые апострофы, как в «Subject matter`»
        s = re.sub(r"[`´]", "", s).strip()

        # Определяем ближайшую непустую строку впереди
        j = i + 1
        next_non_empty = ""
        while j < len(raw_lines):
            nxt = unicodedata.normalize("NFKC", raw_lines[j]).replace("\xa0", " ").strip()
            if nxt:
                next_non_empty = nxt
                break
            j += 1

        # Пропускаем одиночные маркеры только если после них нет никакого текста
        if re.match(r"^\(?\d+\)?$", s) or re.match(r"^\([a-zA-Z]\)$", s) or re.match(r"^\[\d+\]$", s):
            if not next_non_empty:
                i += 1
                continue

        if s in {";", "."}:
            i += 1
            continue

        lines.append(s)
        i += 1
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # убираем служебные строки ELI футера EUR-Lex
    cleaned = re.sub(r"(?im)^\s*ELI:\s*\S+.*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = _unwrap_soft_linebreaks(cleaned)
    return cleaned.strip()

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
    # Нормализуем сразу (NBSP → пробелы, NFKC)
    text = unicodedata.normalize("NFKC", raw_text).replace("\xa0", " ").strip()

    # ---- Сначала найдем все границы Articles и Annexes ----
    boundaries = []

    # Вспомогательная валидация: это реально шапка статьи, а не кросс-ссылка
    def _article_header_is_valid(t: str, start: int, end: int) -> bool:
        # 1) хвост ТЕКУЩЕЙ строки сразу после "Article N" не должен выглядеть как продолжение предложения
        line_end = t.find("\n", end)
        if line_end == -1:
            line_end = len(t)
        tail = t[end:line_end].strip()
        if tail and (tail[:1].islower() or TITLE_VERB.search(tail)):
            return False

        block = t[end : end + 1200]
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        # 2) в первых 5 строках — заголовок; либо в первых 10 — начало пунктов "1."
        if any(_is_title_like(_norm_title_text(ln)) for ln in lines[:5]):
            return True
        if any(re.match(r"^\d+\.\s+", ln) for ln in lines[:10]):
            return True
        # 3) Билингва "Artikel N" принимается только если это САМА линия заголовка, без хвоста
        mnum = re.match(r"^\s*Article\s+(\d+[a-zA-Z]?)", t[start:end], re.I)
        if mnum:
            n = re.escape(mnum.group(1))
            if any(re.match(fr"(?i)^\s*Artikel\s+{n}\s*$", ln) for ln in lines[:5]):
                return True
        return False

    # Находим заголовки статей и отбрасываем кросс-ссылки
    for m in ARTICLE_BOUNDARY_RE.finditer(text):
        if _article_header_is_valid(text, m.start(), m.end()):
            boundaries.append(("Article", m.start(), m.group(0).strip()))

    # Находим все Annexes (case insensitive)
    for match in re.finditer(r"(?i)(?m)^(\s*ANNEX\s+[IVXLC]+\b)", text):
        boundaries.append(("Annex", match.start(), match.group(1).strip()))

    # Находим структурные заголовки (CHAPTER/SECTION/…); используем их как мягкие границы
    for match in STRUCT_BOUNDARY_RE.finditer(text):
        boundaries.append(("Divider", match.start(), match.group(0).strip()))

    # Сортируем по позиции в тексте
    boundaries.sort(key=lambda x: x[1])

    # Убираем Divider, которые сразу следуют за Article без текста между ними
    cleaned = []
    for b in boundaries:
        if (
            b[0] == "Divider"
            and cleaned
            and cleaned[-1][0] == "Article"
        ):
            prev_start = cleaned[-1][1]
            segment = text[prev_start:b[1]]
            after_header = segment.split("\n", 1)[1] if "\n" in segment else ""
            if not after_header.strip():
                # CHAPTER/SECTION сразу после заголовка статьи — не граница
                continue
        cleaned.append(b)
    boundaries = cleaned

    # ---- Обрабатываем каждый блок ----
    for i, (block_type, start_pos, header) in enumerate(boundaries):
        # Определяем конец блока:
        #  - для Article: ближайшая следующая граница (включая 'Divider'),
        #    чтобы не тянуть CHAPTER/SECTION в контент статьи
        #  - для Annex: пропускаем все 'Divider' (SECTION/PART внутри приложения),
        #    пока не встретим реальную границу (Article/Annex) или конец текста
        if block_type == "Annex":
            j = i + 1
            while j < len(boundaries) and boundaries[j][0] == "Divider":
                j += 1
            end_pos = boundaries[j][1] if j < len(boundaries) else len(text)
        else:
            if i + 1 < len(boundaries):
                end_pos = boundaries[i + 1][1]
            else:
                end_pos = len(text)
        block_text = text[start_pos:end_pos].strip()

        # 'Divider' — техническая граница, правил не создаём
        if block_type == "Divider":
            continue

        if block_type == "Article":
            # Парсим Article
            lines = block_text.splitlines()
            # ВАЖНО: без \b после номера — сразу после цифр может идти 'Artikel 97'
            m = re.match(r"\s*Article\s+(\d+[a-zA-Z]?)(.*)", lines[0], re.I)
            if m:
                code = m.group(1).strip()
                if code[-1].isalpha():
                    code = f"{code[:-1]}{code[-1].lower()}"
                rest = (m.group(2) or "")
                # Сносим склейку "Artikel 97" и нормализуем хвост
                rest = re.sub(r"(?i)^\s*Artikel\s+\d+[a-zA-Z]?\s*", "", rest).strip()
                t0 = _norm_title_text(rest)
                title = t0 if _is_title_like(t0) else ""
                title_line_idx = 0
                if not title:
                    marker_seen = False
                    # 1-й проход: «до пунктов»
                    for k in range(1, min(20, len(lines))):
                        cand = unicodedata.normalize("NFKC", lines[k]).replace("\xa0", " ").strip()
                        if not cand:
                            continue
                        if re.match(r"^(ANNEX|Article)\b", cand, re.I):
                            break
                        if re.match(r"^(\(?\d+\)?|\d+\.|\([a-zA-Z]\))", cand):
                            marker_seen = True
                            continue
                        if marker_seen:
                            break
                        cand_norm = _norm_title_text(cand)
                        if _is_title_like(cand_norm) and not END_PUNCT.search(cand_norm) and not ALL_CAPS_ROMAN.fullmatch(cand_norm):
                            title = cand_norm
                            title_line_idx = k
                            break
                # 2-й проход (fallback): если не нашли — ищем в первых 50 строках даже после начала пунктов
                if not title:
                    for k in range(1, min(50, len(lines))):
                        cand = unicodedata.normalize("NFKC", lines[k]).replace("\xa0", " ").strip()
                        if not cand:
                            continue
                        if re.match(r"^(ANNEX|Article)\b", cand, re.I):
                            break
                        if ENUM_PREFIX.match(cand):
                            continue
                        cand_norm = _norm_title_text(cand)
                        # Не брать в качестве заголовка строки, явно продолжающие предложение
                        if _is_hard_title_candidate(cand_norm) and not TITLE_VERB.search(cand_norm[:20]):
                            title = cand_norm
                            title_line_idx = k
                            break
                rule_title = (title or None)
                raw = "\n".join(lines[title_line_idx + 1:]).strip()
                content = _sanitize_content(re.sub(r"\n{3,}", "\n\n", raw))
                parent_code = canonicalize(f"Article{code}")
                rules.append({
                    "section_code": parent_code,
                    "title": rule_title,
                    "content": content,
                })
                _parse_article_subsections(rules, parent_code, content)
        
        elif block_type == "Annex":
            # Парсим Annex
            lines = block_text.splitlines()
            header_line = lines[0]
            m = re.match(r"(?i)^\s*ANNEX\s+([IVXLC]+)\b(?:\s+(.*))?$", header_line)
            if m:
                roman = m.group(1).upper()
                annex_title = (m.group(2) or "").strip()
                consumed = 0

                if annex_title:
                    # Убираем французский дубль, бэктики и левую пунктуацию
                    t = re.sub(r"(?i)\bANNEXE\s+[IVXLC]+\b", "", annex_title).strip()
                    t = _clean_title_piece(t)
                    t = re.sub(r"^[\u2013\u2014\-:;,\.]\s*", "", t)
                    annex_title = re.split(r"\s{2,}", t)[0].strip()
                if annex_title and (not _is_title_like(annex_title) or TITLE_VERB.search(annex_title) or END_PUNCT.search(annex_title)):
                    annex_title = ""

                if not annex_title:
                    # Берём ТОЛЬКО первую «title-like» строку после заголовка (до 40 строк)
                    k = 1
                    first_title = ""
                    while k < min(40, len(lines)):
                        t_norm = unicodedata.normalize("NFKC", lines[k]).replace("\xa0", " ").strip()
                        if not t_norm:
                            k += 1
                            continue
                        # Стоп по служебным подсекциям/маркерам/знакам
                        if re.match(r"^(Section|Part|Chapter|Titre|Sezione|Kapitel)\b", t_norm, re.I):
                            break
                        if re.match(r"^\d+\.\s+|\([a-zA-Z]\)\s+", t_norm):
                            break
                        if t_norm[:1] in {",", "—", "–", "-", ";", "."}:
                            break
                        t_norm = _clean_title_piece(re.sub(r"^[\u2013\u2014\-:;,\.]\s*", "", t_norm))
                        # Если строка выглядит как обычное предложение с глаголом — это уже контент, не title
                        if TITLE_VERB.search(t_norm) or END_PUNCT.search(t_norm) or ALL_CAPS_ROMAN.fullmatch(t_norm):
                            break
                        if not _is_title_like(t_norm):
                            break
                        first_title = t_norm
                        k += 1
                        break
                    annex_title = first_title
                    consumed = (k - 1) if annex_title else 0

                raw_body = "\n".join(lines[1 + consumed:]).strip()
                body = _sanitize_content(re.sub(r"\n{3,}", "\n\n", raw_body))

                parent_code = canonicalize(f"Annex{roman}")
                rules.append({
                    "section_code": parent_code,
                    "title": (annex_title or None),
                    "content": body,
                })

                # Внутри Annex парсим подразделы
                _parse_annex_subsections(rules, parent_code, body)

    return rules


def _parse_article_subsections(rules: List[dict], parent_code: str, body: str):
    """Парсит пункты и подпункты внутри Article."""
    # Разрешаем только подпункты 1..999, исключаем года/большие числа
    top_parts = re.split(r"(?m)^\s*([1-9]\d{0,2})\.\s+", body)
    if len(top_parts) >= 3:
        for i in range(1, len(top_parts), 2):
            num = top_parts[i]
            text_i = top_parts[i + 1] if i + 1 < len(top_parts) else ""
            lines_i_raw = text_i.strip().splitlines()
            lines_i = [unicodedata.normalize("NFKC", ln).replace("\xa0", " ").strip() for ln in lines_i_raw]
            content_i = _sanitize_content("\n".join(lines_i).strip())
            code_i = canonicalize(f"{parent_code}.{num}")
            rules.append({
                "section_code": code_i,
                "title": None,
                "content": content_i,
                "parent_section_code": canonicalize(parent_code),
                "order_index": format_order_index(num),
            })
            sub_parts = re.split(r"(?m)^\s*\(([a-zA-Z])\)\s+", content_i)
            if len(sub_parts) >= 3:
                for j in range(1, len(sub_parts), 2):
                    letter = sub_parts[j].lower()
                    text_j = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
                    lines_j_raw = text_j.strip().splitlines()
                    lines_j = [unicodedata.normalize("NFKC", ln).replace("\xa0", " ").strip() for ln in lines_j_raw]
                    content_j = _sanitize_content("\n".join(lines_j).strip())
                    sub_code = canonicalize(f"{code_i}.{letter}")
                    rules.append({
                        "section_code": sub_code,
                        "title": None,
                        "content": content_j,
                        "parent_section_code": code_i,
                        "order_index": format_order_index(letter),
                    })


def _parse_annex_subsections(rules: List[dict], parent_code: str, body: str):
    """Парсит подразделы внутри Annex."""
    # Разрежем по верхнему уровню "N." (в начале строки)
    # Разрешаем только подпункты 1..999, исключаем года/большие числа
    top_parts = re.split(r"(?m)^\s*([1-9]\d{0,2})\.\s+", body)
    # split даёт: ["intro", "1", "text1", "2", "text2", ...]
    if len(top_parts) >= 3:
        for i in range(1, len(top_parts), 2):
            num = top_parts[i]
            text_i = top_parts[i + 1] if i + 1 < len(top_parts) else ""
            code_i = canonicalize(f"{parent_code}.{num}")
            lines_i = [unicodedata.normalize("NFKC", ln).replace("\xa0", " ").strip() for ln in text_i.splitlines()]
            body_i = _sanitize_content("\n".join(lines_i).strip())
            rules.append({
                "section_code": code_i,
                "title": None,
                "content": body_i,
                "parent_section_code": canonicalize(parent_code),
                "order_index": format_order_index(num),
            })
            # Разрезаем подпункты (a), (b) ...
            sub_parts = re.split(r"(?m)^\s*\(([a-zA-Z])\)\s+", body_i)
            if len(sub_parts) >= 3:
                for j in range(1, len(sub_parts), 2):
                    letter = sub_parts[j].lower()
                    text_j = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
                    lines_j = [unicodedata.normalize("NFKC", ln).replace("\xa0", " ").strip() for ln in text_j.splitlines()]
                    body_j = _sanitize_content("\n".join(lines_j).strip())
                    sub_code = canonicalize(f"{code_i}.{letter}")
                    rules.append({
                        "section_code": sub_code,
                        "title": None,
                        "content": body_j,
                        "parent_section_code": code_i,
                        "order_index": format_order_index(letter),
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
    def update(self, name: str, version: str, url: str, celex_id: str) -> Regulation:
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

        # Fetch current text, using cache only as an optimization
        cached = self.get_cached_text(url)
        raw_text = fetch_regulation_text(url)
        # Сохраняем свежую версию для последующих запусков независимо от кэша
        self.save_cached_text(url, raw_text)
        clean_text = _sanitize_content(raw_text)
        content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

        same_hash_reg = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id, content_hash=content_hash)
            .order_by(Regulation.effective_date.desc())
            .first()
        )
        if same_hash_reg:
            updated = False
            # Не затираем что-то осмысленное на None
            if version is not None and same_hash_reg.version != version:
                same_hash_reg.version = version
                updated = True
            if same_hash_reg.effective_date is None:
                same_hash_reg.effective_date = datetime.utcnow()
                updated = True
            if updated:
                rules_q = self.db.query(Rule).filter_by(regulation_id=same_hash_reg.id)
                for r in rules_q:
                    if version is not None and r.version != version:
                        r.version = version
                    if same_hash_reg.effective_date and r.effective_date is None:
                        r.effective_date = same_hash_reg.effective_date
                self.db.commit()
            return same_hash_reg

        # Retrieve the most recent previous version (if any)
        previous_reg = (
            self.db.query(Regulation)
            .filter(Regulation.celex_id == celex_id)
            .order_by(Regulation.effective_date.desc(), Regulation.last_updated.desc())
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
            content_hash=content_hash,
        )
        self.db.add(reg)
        self.db.flush()  # get ID for FK relations

        # Парсим и вставляем новые правила (с поддержкой parent_rule_id для Annex)
        code_to_rule = {}
        for rule_data in parse_rules(clean_text):
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


def update_regulation(db: Session, name: str, version: str, url: str, celex_id: str) -> Regulation:
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
