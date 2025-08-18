# regulation_monitor_v2.py
"""Production-grade мониторинг регуляторов с мультисорс-фетчингом.

Этот модуль расширяет базовый RegulationMonitor поддержкой:
- Асинхронного мультисорс-фетчинга
- ELI SPARQL и RSS-источников
- Надёжной сети с tenacity retry
- Event-driven архитектуры
- Этичного скрапинга
"""

import asyncio
import hashlib
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import aiohttp
from sqlalchemy.orm import Session
from tenacity import retry, wait_exponential_jitter, stop_after_attempt
import unicodedata
from yarl import URL

from .models import (
    Regulation, Rule, DocumentRuleMapping, ComplianceAlert,
    Source, RegulationSourceLog, Document
)
from .rss_listener import fetch_rss_feed, RSSMonitor
import re

logger = logging.getLogger(__name__)

# User-Agent для этичного скрапинга
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "Annex4ComplianceBot/1.2 (+https://your-domain.example/contact)"
)


def _stable_oj_url(celex: str) -> str:
    """Return a stable Official Journal EN URL for the given CELEX id."""
    kind_map = {"R": "reg", "L": "dir", "D": "dec"}
    # CELEX консолидированных текстов: 0 + YEAR + TYPE + NUMBER + '-' + YYYYMMDD
    m_cons = re.match(r"^0(\d{4})([A-Z])(\d+)-\d{8}$", celex, re.I)
    if m_cons:
        year, kind, num = m_cons.group(1), m_cons.group(2).upper(), int(m_cons.group(3))
        seg = kind_map.get(kind, kind.lower())
        return f"https://eur-lex.europa.eu/eli/{seg}/{year}/{num}/oj/eng"
    # Базовые акты, например 32024R1689
    m_base = re.match(r"^3(\d{4})([A-Z])(\d+)$", celex, re.I)
    if m_base:
        year, kind, num = m_base.group(1), m_base.group(2).upper(), int(m_base.group(3))
        seg = kind_map.get(kind, kind.lower())
        return f"https://eur-lex.europa.eu/eli/{seg}/{year}/{num}/oj/eng"
    return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A{celex}"


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

class RegulationMonitorV2:
    """Production-grade монитор регуляторов с мультисорс-поддержкой."""
    
    def __init__(self, db: Session, config_path: Optional[Path] = None):
        self.db = db
        self.rss_monitor = RSSMonitor()
        
        # Загружаем конфигурацию
        if config_path is None:
            config_path = Path(__file__).parent / "sources.yaml"
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Инициализируем источники в БД
        self._init_sources()

    def _init_sources(self):
        """Инициализировать источники в базе данных."""
        for source_config in self.config["sources"]:
            source = (
                self.db.query(Source)
                .filter_by(id=source_config["id"])
                .first()
            )

            # Выделяем дополнительные поля, которые нужно сохранить в Source.extra
            extra_fields = {
                k: v
                for k, v in source_config.items()
                if k
                not in {"id", "url", "type", "freq", "active", "description"}
            }
            cfg_active = bool(source_config.get("active", True))

            if not source:
                source = Source(
                    id=source_config["id"],
                    url=source_config["url"],
                    type=source_config["type"],
                    freq=source_config["freq"],
                    active=cfg_active,
                    extra=extra_fields or None,
                )
                self.db.add(source)
            else:
                # Обновляем дополнительные параметры и активность (URL/тип не трогаем)
                if extra_fields:
                    source.extra = extra_fields
                source.active = cfg_active

        self.db.commit()
        logger.info(f"Initialized {len(self.config['sources'])} sources")

    async def update_by_type(self, source_type: str) -> Dict[str, int]:
        """Обновить активные источники указанного типа."""
        active_sources = (
            self.db.query(Source)
            .filter_by(active=True, type=source_type)
            .all()
        )

        tasks: List[asyncio.Task] = []
        async with aiohttp.ClientSession(
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            }
        ) as session:
            for source in active_sources:
                if source_type == "eli_sparql":
                    tasks.append(self._process_eli_source(source, session))
                elif source_type == "rss":
                    tasks.append(self._process_rss_source(source, session))
                elif source_type == "html":
                    tasks.append(self._process_html_source(source, session))
                # press_api больше не используем: у Presscorner нет публичного /api/events
                # RSS уже покрывает этот источник.

            results = await asyncio.gather(*tasks, return_exceptions=True)
        stats = {"type": source_type, "processed": 0, "errors": 0}
        for result in results:
            if isinstance(result, Exception):
                stats["errors"] += 1
                logger.error(
                    f"Source processing error ({type(result).__name__}): {result}"
                )
            elif result:
                stats["processed"] += 1
        return stats

    async def update_eli_sources(self) -> Dict[str, int]:
        return await self.update_by_type("eli_sparql")

    async def update_rss_sources(self) -> Dict[str, int]:
        return await self.update_by_type("rss")

    async def update_html_sources(self) -> Dict[str, int]:
        return await self.update_by_type("html")
    
    async def update_all(self) -> Dict[str, int]:
        """Обновить все активные источники асинхронно.
        
        Returns
        -------
        Dict[str, int]
            Статистика обновлений по типам источников
        """
        active_sources = self.db.query(Source).filter_by(active=True).all()

        # Группируем источники по типам
        eli_sources = [s for s in active_sources if s.type == "eli_sparql"]
        rss_sources = [s for s in active_sources if s.type == "rss"]
        html_sources = [s for s in active_sources if s.type == "html"]
        
        # Создаём задачи для асинхронного выполнения
        tasks: List[asyncio.Task] = []
        async with aiohttp.ClientSession(
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            }
        ) as session:
            # ELI SPARQL источники
            for source in eli_sources:
                tasks.append(self._process_eli_source(source, session))

            # RSS источники
            for source in rss_sources:
                tasks.append(self._process_rss_source(source, session))

            # HTML источники
            for source in html_sources:
                tasks.append(self._process_html_source(source, session))


            # Выполняем все задачи параллельно пока сессия открыта
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем статистику
        stats = {"eli_sparql": 0, "rss": 0, "html": 0, "errors": 0}
        for result in results:
            if isinstance(result, Exception):
                stats["errors"] += 1
                logger.error(
                    f"Source processing error ({type(result).__name__}): {result}"
                )
            elif result:
                source_type = result.get("type", "unknown")
                stats[source_type] += 1
        
        # Добавляем общее количество обработанных источников
        stats["total"] = stats["eli_sparql"] + stats["rss"] + stats["html"]
        
        logger.info(f"Update completed: {stats}")
        return stats
    
    async def _process_eli_source(
        self,
        source: Source,
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать ELI SPARQL источник."""
        logger.info(f"Starting _process_eli_source for source: {source.id}")
        fetch_mode = "unknown"
        try:
            # Получаем настройки из Source.extra
            extra = source.extra or {}

            # CELEX ID может быть в extra, атрибуте модели или в URL
            celex_id = (
                extra.get("celex_id")
                or getattr(source, "celex_id", None)
                or self._extract_celex_id(source.url)
            )

            endpoint = extra.get(
                "endpoint", "https://publications.europa.eu/webapi/rdf/sparql"
            )

            meta_date: Optional[str] = None
            if extra.get("consolidated") and celex_id:
                latest = await self._resolve_latest_consolidated_celex(
                    session, celex_id, endpoint
                )
                if latest:
                    celex_id, meta_date = latest
                else:
                    logger.warning(f"No consolidated CELEX found for base {celex_id}")
                    self._log_source_operation(source.id, "error", None, None, "No consolidated CELEX")
                    return None
            logger.info(f"Using CELEX ID: {celex_id} for source: {source.id}")
            if not celex_id:
                logger.warning(f"No CELEX ID found for source {source.id}")
                return None

            eli_data = await self._execute_sparql_query(session, endpoint, celex_id)
            logger.info(f"SPARQL data received: {eli_data is not None}")

            # Версию и дату берём из SPARQL/консолидации; если даты нет — парсим из суффикса CELEX (....-YYYYMMDD)
            meta_version = eli_data.get('version') if eli_data else None
            meta_date = (eli_data.get('date') if eli_data else None) or meta_date
            if extra.get("consolidated") and celex_id and "-" in celex_id and not meta_date:
                m = re.match(r".*-(\d{8})$", celex_id)
                if m:
                    d = m.group(1)
                    meta_date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            if not meta_version and meta_date:
                meta_version = meta_date.replace("-", "")

            fetch_mode = "sparql_item"
            txt: Optional[str] = None
            pdf = html = None

            if eli_data:
                items = eli_data.get("items") or []
                pdf = next((i for i in items if i.get("format", "").upper().find("PDF") >= 0), None)
                html = next((i for i in items if i.get("format", "").upper().find("HTML") >= 0), None)
                try:
                    if pdf:
                        txt = await self._fetch_pdf_text(session, pdf["url"])
                        if (not txt or len(txt) < 300) and html:
                            txt = await self._fetch_html_text(session, html["url"])
                    elif html:
                        txt = await self._fetch_html_text(session, html["url"])
                except Exception as e:
                    url_err = (pdf or html or {}).get("url")
                    logger.warning(f"Failed to fetch item {url_err}: {e}")

            if not txt:
                logger.warning("SPARQL failed or returned no text; falling back to HTML-only ingestion")
                if eli_data:
                    fetch_mode = "sparql_meta_html_text"
                else:
                    fetch_mode = "html_fallback"
                url = _stable_oj_url(celex_id)
                try:
                    txt = await self._fetch_html_text(session, url)
                except Exception:
                    m = re.match(r"^3(\d{4})([A-Z])(\d+)$", celex_id, re.I)
                    if m:
                        year, kind, num = m.group(1), m.group(2).upper(), int(m.group(3))
                        seg = {"R": "reg", "L": "dir", "D": "dec"}.get(kind, kind.lower())
                        backup = f"https://eur-lex.europa.eu/eli/{seg}/{year}/{num}/oj/eng"
                        txt = await self._fetch_html_text(session, backup)
                if not txt:
                    logger.warning("No text via HTML; skipping.")
                    return None
                title = (eli_data.get('title') if eli_data else None) or f"Regulation {celex_id}"
                version = meta_version or (meta_date.replace("-", "") if meta_date else None)
                clean = self._sanitize_text(txt)
                content_hash = hashlib.sha256(clean.encode()).hexdigest()
                has_changed = self._has_content_changed(source.id, content_hash)
                if has_changed:
                    self._ingest_regulation_text(
                        name=title,
                        version=version,
                        text=clean,
                        url=url,
                        celex_id=celex_id,
                        expression_version=meta_version,
                        work_date=meta_date,
                    )
                self._log_source_operation(source.id, "success", content_hash, len(clean.encode()), None, fetch_mode)
                return {"type": "eli_sparql", "source_id": source.id}

            # Обработка текста и метаданных
            clean = self._sanitize_text(txt)
            content_hash = hashlib.sha256(clean.encode()).hexdigest()
            logger.info(f"Content hash: {content_hash[:16]}...")
            has_changed = self._has_content_changed(source.id, content_hash)
            logger.info(f"Content has changed: {has_changed}")
            name = eli_data.get('title') if eli_data else None
            # Только нормальное имя: ELI title или безопасный дефолт
            name = name or f"Regulation {celex_id}"
            expr_version = meta_version
            date = meta_date
            version = expr_version or (date.replace("-", "") if date else None)
            if has_changed:
                regulation = self._ingest_regulation_text(
                    name=name,
                    version=version,
                    text=clean,
                    url=((pdf or html or {}).get("url")) or _stable_oj_url(celex_id),
                    celex_id=celex_id,
                    expression_version=expr_version,
                    work_date=date,
                )
                logger.info(f"Updated regulation from SPARQL source {source.id}: {regulation.name}")
            else:
                logger.info("No changes detected, skipping regulation update")
            self._log_source_operation(source.id, "success", content_hash, len(clean.encode()), None, fetch_mode)
            return {"type": "eli_sparql", "source_id": source.id}
        except aiohttp.ClientResponseError as e:
            self.db.rollback()
            logger.error(
                "HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            self._log_source_operation(
                source.id, "error", None, None, f"HTTP {e.status} {e.message}", fetch_mode
            )
            return None
        except Exception as e:
            logger.exception("%s processing %s", type(e).__name__, source.id)
            self.db.rollback()
            self._log_source_operation(source.id, "error", None, None, str(e), fetch_mode)
            return None
    
    async def _process_rss_source(
        self, 
        source: Source, 
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать RSS источник."""
        try:
            # Получаем RSS-фид
            entries = await fetch_rss_feed(source.url)

            new_entries = []
            for link, content_hash, title in entries:
                exists = (
                    self.db.query(RegulationSourceLog)
                    .filter_by(source_id=source.id, content_hash=content_hash)
                    .first()
                )
                if not exists:
                    new_entries.append((link, content_hash, title))
                    # Логируем уникальный элемент
                    self._log_source_operation(
                        source.id, "success", content_hash, None, None, "rss_item"
                    )

            # Логируем сам факт обновления фида
            self._log_source_operation(
                source.id,
                "success",
                hashlib.sha256(str(entries).encode()).hexdigest(),
                len(str(entries).encode()),
                None,
                "rss_feed",
            )

            # Создаём алерты для новых элементов
            for link, content_hash, title in new_entries:
                self._create_rss_alert(source.id, title, link)

            return {
                "type": "rss",
                "source_id": source.id,
                "new_entries": len(new_entries),
            }
            
        except aiohttp.ClientResponseError as e:
            self.db.rollback()
            logger.error(
                "HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            self._log_source_operation(
                source.id, "error", None, None, f"HTTP {e.status} {e.message}"
            )
            return None
        except Exception as e:
            logger.exception("%s processing %s", type(e).__name__, source.id)
            self.db.rollback()
            self._log_source_operation(source.id, "error", None, None, str(e))
            return None
    
    async def _process_html_source(
        self, 
        source: Source, 
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать HTML источник (fallback)."""
        try:
            celex_id = self._extract_celex_id(source.url)
            url = _stable_oj_url(celex_id) if celex_id else source.url
            # ВАЖНО: всегда преобразуем HTML -> плоский текст
            try:
                text = await self._fetch_html_text(session, url)
            except Exception:
                url = source.url
                async with session.get(URL(url, encoded=True)) as resp:
                    resp.raise_for_status()
                    html = await resp.text()
                from bs4 import BeautifulSoup
                text = BeautifulSoup(html, "html.parser").get_text(separator="\n")
            clean = self._sanitize_text(text)
            content_hash = hashlib.sha256(clean.encode()).hexdigest()
            has_changed = self._has_content_changed(source.id, content_hash)
            celex_id = celex_id or "UNKNOWN"
            name = None

            work_date = None
            expression_version = None
            existing = (
                self.db.query(Regulation)
                .filter_by(celex_id=celex_id, content_hash=content_hash)
                .first()
            )
            if existing:
                if existing.work_date:
                    work_date = existing.work_date.strftime("%Y-%m-%d")
                if existing.expression_version:
                    expression_version = existing.expression_version
            else:
                try:
                    from .eli_client import fetch_latest_eli

                    meta = await fetch_latest_eli(session, celex_id)
                    if meta:
                        work_date = work_date or meta.get("date")
                        expression_version = expression_version or meta.get("version")
                        eli_title = meta.get("title")
                        if eli_title:
                            name = eli_title
                except Exception:
                    pass

            if work_date and "T" in work_date:
                work_date = work_date.split("T", 1)[0]

            # Версия только из реальных метаданных
            if expression_version:
                version_str = expression_version
            elif work_date:
                version_str = work_date.replace("-", "")
            else:
                version_str = None

            # Только нормальное имя: ELI title или безопасный дефолт
            name = name or f"Regulation {celex_id}"

            regulation = self._ingest_regulation_text(
                name=name,
                version=version_str,
                text=clean,
                url=url,
                celex_id=celex_id,
                expression_version=expression_version,
                work_date=work_date,
            )

            if has_changed:
                logger.info(f"Updated regulation from HTML source {source.id}")
            self._log_source_operation(
                source.id, "success", content_hash, len(clean.encode()), None, "html"
            )

            return {"type": "html", "source_id": source.id}
            
        except aiohttp.ClientResponseError as e:
            self.db.rollback()
            logger.error(
                "HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            self._log_source_operation(
                source.id, "error", None, None, f"HTTP {e.status} {e.message}", "html"
            )
            return None
        except Exception as e:
            logger.exception("%s processing %s", type(e).__name__, source.id)
            self.db.rollback()
            self._log_source_operation(source.id, "error", None, None, str(e), "html")
            return None
    
    async def _execute_sparql_query(
        self, session: aiohttp.ClientSession, endpoint: str, celex_id: str
    ) -> Optional[Dict]:
        """Получить данные через SPARQL используя общий ELI клиент."""
        try:
            from .eli_client import fetch_latest_eli

            return await fetch_latest_eli(session, celex_id, endpoint)
        except Exception as e:
            logger.error(f"ELI SPARQL fetch failed for {celex_id}: {e}")
            return None

    async def _resolve_latest_consolidated_celex(
        self, session: aiohttp.ClientSession, base_celex: str, endpoint: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Найти последний консолидированный CELEX и дату для базового идентификатора."""
        base = (base_celex or "").strip().upper()
        if not re.match(r"^[0-9A-Z]+$", base) or len(base) < 2:
            return None
        prefix = f"0{base[1:]}-"
        query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?celex ?date WHERE {{
          ?work cdm:resource_legal_id_celex ?celex .
          FILTER(STRSTARTS(?celex, "{prefix}"))
          OPTIONAL {{ ?work cdm:work_date_document ?date }}
        }}
        ORDER BY DESC(?date) DESC(?celex)
        LIMIT 1
        """
        params = {"query": query, "format": "application/sparql-results+json"}
        try:
            async with session.get(
                endpoint,
                params=params,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/sparql-results+json",
                    "Accept-Language": "en",
                },
                timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientResponseError as e:
            logger.error(
                "Failed to resolve consolidated CELEX: HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            return None
        except Exception as e:
            logger.error("Failed to resolve consolidated CELEX for %s: %s", base_celex, e)
            return None
        rows = data.get("results", {}).get("bindings", [])
        if not rows:
            return None
        celex_val = rows[0]["celex"]["value"]
        date_val = rows[0].get("date", {}).get("value")
        if not date_val:
            m = re.match(r".*-(\d{8})$", celex_val)
            if m:
                d = m.group(1)
                date_val = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        return celex_val, date_val

    async def _fetch_html_text(self, session: aiohttp.ClientSession, url: str) -> str:
        """Получить текст из HTML-страницы с уважением к robots.txt."""
        from .ethical_fetcher import ethical_fetch

        try:
            html = await ethical_fetch(
                session,
                url,
                user_agent=UA,
            )
        except aiohttp.ClientResponseError as e:
            logger.error(
                "HTTP %s %s; url=%s; headers=%s",
                e.status,
                e.message,
                e.request_info.real_url,
                e.headers,
            )
            raise
        if not html:
            raise RuntimeError(f"HTML fetch failed for {url}")

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n")

    def _sanitize_text(self, text: str) -> str:
        """Нормализовать текст перед хешированием и парсингом."""
        text = unicodedata.normalize("NFKC", text or "")
        # выкидываем простые «висячие» сноски в конце строк
        text = re.sub(r"\s\[\d+\]\s*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*[\(\[]?\d+[\)\]]?\s*$", "", text, flags=re.MULTILINE)
        # схлопываем пробелы/пустые абзацы
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = _unwrap_soft_linebreaks(text)
        return text.strip()

    async def _fetch_pdf_text(self, session: aiohttp.ClientSession, url: str) -> str:
        """Получить текст из PDF-документа."""
        import io
        import pdfplumber

        async with session.get(
            url,
            headers={'User-Agent': UA, 'Accept': 'application/pdf'},
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            data = await resp.read()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(pages)
    
    def _extract_celex_id(self, url: str) -> Optional[str]:
        """Извлечь CELEX ID из URL."""
        import re
        logger.info(f"Extracting CELEX ID from URL: {url}")
        match = re.search(r'(?:CELEX%3A|CELEX:)([A-Z0-9]+)', url, re.IGNORECASE)
        if match:
            celex_id = match.group(1)
            logger.info(f"Extracted CELEX ID: {celex_id}")
            return celex_id
        logger.warning(f"No CELEX ID found in URL: {url}")
        return None
    
    def _has_content_changed(self, source_id: str, content_hash: str) -> bool:
        """Проверить, изменился ли контент источника."""
        last_log = (
            self.db.query(RegulationSourceLog)
            .filter_by(source_id=source_id)
            .order_by(RegulationSourceLog.fetched_at.desc())
            .first()
        )
        
        logger.info(f"Checking content change for source {source_id}")
        logger.info(f"Last log: {last_log}")
        logger.info(f"Current hash: {content_hash[:16]}...")
        if last_log:
            logger.info(f"Last hash: {last_log.content_hash[:16] if last_log.content_hash else 'None'}...")
        
        if not last_log or last_log.content_hash != content_hash:
            logger.info(f"Content has changed: {not last_log or last_log.content_hash != content_hash}")
            return True
        logger.info("Content has not changed")
        return False

    def _log_source_operation(
        self,
        source_id: str,
        status: str,
        content_hash: Optional[str],
        bytes_downloaded: Optional[int],
        error_message: Optional[str],
        fetch_mode: Optional[str] = None
    ):
        """Логировать операцию с источником."""
        log = RegulationSourceLog(
            source_id=source_id,
            status=status,
            content_hash=content_hash,
            bytes_downloaded=bytes_downloaded,
            error_message=error_message,
            fetch_mode=fetch_mode
        )
        self.db.add(log)
        # Обновляем last_fetched для источника при любом успешном событии
        if status == "success":
            src = self.db.query(Source).filter_by(id=source_id).first()
            if src:
                src.last_fetched = datetime.utcnow()
        self.db.commit()

    def _relink_children(
        self,
        parent: Rule,
        old_code: str,
        new_code: str,
        code_to_rule: Dict[str, Rule],
    ) -> None:
        """Propagate section code change to all descendants."""
        from .regulation_monitor import canonicalize

        children = self.db.query(Rule).filter_by(parent_rule_id=parent.id).all()
        for child in children:
            child_code = canonicalize(child.section_code)
            if not child_code.startswith(f"{old_code}."):
                continue
            new_child_code = canonicalize(new_code + child_code[len(old_code):])
            if child_code in code_to_rule:
                del code_to_rule[child_code]
            child.section_code = new_child_code
            code_to_rule[new_child_code] = child
            self._relink_children(child, child_code, new_child_code, code_to_rule)
    
    def _ingest_regulation_text(
        self,
        name: str,
        version: str,
        text: str,
        url: str,
        celex_id: str = "UNKNOWN",
        expression_version: Optional[str] = None,
        work_date: Optional[str] = None,
    ) -> Regulation:
        """Ингестировать текст регуляции в базу данных."""
        from .regulation_monitor import (
            parse_rules,
            canonicalize,
            format_order_index,
            _sanitize_content,
        )
        from .legal_diff import LegalDiffAnalyzer
        import hashlib

        expression_version = expression_version or version

        work_date_dt = None
        if work_date:
            try:
                work_date_dt = datetime.fromisoformat(work_date)
            except Exception:
                try:
                    from dateutil import parser as _dtparser  # optional
                    work_date_dt = _dtparser.parse(work_date)
                except Exception:
                    logger.warning("Unparsed work_date: %r", work_date)
                    work_date_dt = None

        normalized_text = _sanitize_content(text)
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

        existing_version = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id, version=version)
            .first()
        )
        if existing_version:
            return existing_version

        same_hash_reg = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id, content_hash=content_hash)
            .order_by(Regulation.effective_date.desc())
            .first()
        )
        if same_hash_reg:
            updated = False
            if version is not None and same_hash_reg.version != version:
                same_hash_reg.version = version
                updated = True
            if expression_version and not same_hash_reg.expression_version:
                same_hash_reg.expression_version = expression_version
                updated = True
            if work_date_dt and not same_hash_reg.work_date:
                same_hash_reg.work_date = work_date_dt
                same_hash_reg.effective_date = work_date_dt
                updated = True
            if updated:
                if version is not None:
                    rules_q = self.db.query(Rule).filter_by(regulation_id=same_hash_reg.id)
                    for r in rules_q:
                        if r.version != version:
                            r.version = version
                        if work_date_dt and r.effective_date is None:
                            r.effective_date = work_date_dt
                self.db.commit()
            return same_hash_reg

        prev_reg = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id)
            .order_by(Regulation.effective_date.desc(), Regulation.last_updated.desc())
            .first()
        )

        def infer_risk_level(section_code: str, content: str) -> str:
            hard_high = ("AnnexIV", "Article9", "Article10", "Article11", "Article15")
            code = (section_code or "").lower()
            if any(code.startswith(h.lower()) for h in hard_high):
                base = "high"
            elif code.startswith(("article12", "article13", "article14", "article17")):
                base = "medium"
            else:
                base = "low"
            if re.search(r"\b(shall|must|required|prohibited|penalt|liabilit)\b", content, re.I):
                return "high"
            return base
        # На этом этапе мы уже проверили:
        #  - exact match по (celex_id, version) -> return
        #  - same_hash_reg -> клон и return
        # Значит, это НОВАЯ версия с другим контентом — создаём новую запись.
        regulation = Regulation(
            name=name,
            celex_id=celex_id,
            version=version,
            expression_version=expression_version,
            work_date=work_date_dt,
            source_url=url,
            effective_date=work_date_dt or datetime.utcnow(),
            last_updated=datetime.utcnow(),
            status="active",
        )
        self.db.add(regulation)
        self.db.flush()
        regulation.content_hash = content_hash

        # Парсим правила и формируем карту существующих секций
        rules_data = parse_rules(text)
        for rd in rules_data:
            rd["content"] = _sanitize_content(rd.get("content", ""))
        logger.info("Parsed rules: %d", len(rules_data))
        analyzer = LegalDiffAnalyzer()

        code_to_old: Dict[str, Rule] = {}
        if prev_reg:
            old_rules = (
                self.db.query(Rule)
                .filter_by(regulation_id=prev_reg.id)
                .all()
            )
            for r in old_rules:
                code_to_old[canonicalize(r.section_code)] = r

        code_to_rule: Dict[str, Rule] = {}

        for rule_data in rules_data:
            section_code = canonicalize(rule_data["section_code"])
            parent_code = canonicalize(rule_data.get("parent_section_code")) if rule_data.get("parent_section_code") else None
            if section_code in code_to_rule:
                continue
            old_rule = code_to_old.get(section_code)
            new_norm = _sanitize_content(rule_data["content"])
            t = (rule_data["title"] or "").strip()
            change = None
            if old_rule:
                old_norm = _sanitize_content(old_rule.content or "")
                change = analyzer.analyze_changes(old_norm, new_norm, section_code)

            rule = Rule(
                regulation_id=regulation.id,
                section_code=section_code,
                title=(t or None),
                content=new_norm,
                risk_level=infer_risk_level(section_code, new_norm),
                version=version,
                effective_date=work_date_dt,
                last_modified=work_date_dt or datetime.utcnow(),
                parent_rule_id=None,
                order_index=format_order_index(rule_data.get("order_index")) if rule_data.get("order_index") is not None else None,
                ingested_at=datetime.utcnow(),
            )
            if change and change.change_type == "no_change" and old_rule:
                if work_date_dt and (not old_rule.last_modified or old_rule.last_modified > work_date_dt):
                    rule.last_modified = work_date_dt
                else:
                    rule.last_modified = old_rule.last_modified
            self.db.add(rule)
            self.db.flush()
            code_to_rule[section_code] = rule

            if parent_code and rule.parent_rule_id is None:
                parent = code_to_rule.get(parent_code)
                if parent:
                    rule.parent_rule_id = parent.id

            if change and change.severity in ["high", "critical", "major"]:
                prio = "urgent" if change.severity in ["high", "critical", "major"] else "medium"
                alert = ComplianceAlert(
                    rule_id=rule.id,
                    alert_type="rule_updated",
                    priority=prio,
                    message=f"Rule {section_code} updated: {change.change_type} - {analyzer.get_change_summary(change)}",
                )
                self.db.add(alert)

        # --- Перенос маппингов документов на новые rule_id ---
        if prev_reg and code_to_old:
            changed_codes = set()
            for sc, old_rule in code_to_old.items():
                new_rule = code_to_rule.get(sc)
                if not new_rule:
                    continue
                old_norm = _sanitize_content(old_rule.content or "")
                new_norm = _sanitize_content(new_rule.content or "")
                ch = analyzer.analyze_changes(old_norm, new_norm, sc)
                if ch.change_type != "no_change":
                    changed_codes.add(sc)

            old_rule_ids = [r.id for r in code_to_old.values()]
            mappings = (
                self.db.query(DocumentRuleMapping)
                .filter(DocumentRuleMapping.rule_id.in_(old_rule_ids))
                .all()
            )
            now = datetime.utcnow()
            for m in mappings:
                old_rule_obj = self.db.get(Rule, m.rule_id)
                if not old_rule_obj:
                    continue
                old_sc = old_rule_obj.section_code
                new_rule = code_to_rule.get(canonicalize(old_sc))
                if not new_rule:
                    continue
                self.db.add(DocumentRuleMapping(
                    document_id=m.document_id,
                    rule_id=new_rule.id,
                    confidence_score=m.confidence_score,
                    mapped_by="auto",
                    mapped_at=now,
                    last_verified=now,
                ))
                if canonicalize(old_sc) in changed_codes:
                    doc = self.db.get(Document, m.document_id)
                    if doc:
                        doc.compliance_status = "outdated"
                        doc.last_modified = now
                        self.db.add(ComplianceAlert(
                            document_id=doc.id,
                            rule_id=new_rule.id,
                            alert_type="document_outdated",
                            priority="high",
                            message=f"Document {doc.filename or doc.id} outdated due to changes in {old_sc}",
                        ))

        # Финальный проход для связывания сирот
        self.db.flush()
        orphans = (
            self.db.query(Rule)
            .filter_by(regulation_id=regulation.id, parent_rule_id=None)
            .all()
        )
        for r in orphans:
            canon = canonicalize(r.section_code)
            if r.section_code != canon:
                r.section_code = canon
            if "." in canon:
                p_code = canon.rsplit(".", 1)[0]
                parent = code_to_rule.get(p_code)
                if not parent:
                    parent = (
                        self.db.query(Rule)
                        .filter_by(regulation_id=regulation.id, section_code=p_code)
                        .first()
                    )
                    if parent:
                        code_to_rule[p_code] = parent
                if parent:
                    r.parent_rule_id = parent.id

        self.db.commit()
        return regulation
    
    def _create_rss_alert(self, source_id: str, title: str, link: str):
        """Создать алерт для нового RSS-элемента."""
        alert = ComplianceAlert(
            document_id=None,  # RSS алерты не привязаны к документам
            rule_id=None,
            alert_type="rss_update",
            priority="medium",
            message=f"New regulatory update from {source_id}: {title} - {link}"
        )
        self.db.add(alert)
        self.db.commit()
    
    def _create_press_alert(self, source_id: str, event: Dict):
        """Создать press API алерт."""
        alert = ComplianceAlert(
            document_id=None,
            rule_id=None,
            alert_type="press_release",
            priority="high",
            message=f"New press release from {source_id}: {event.get('title', 'Unknown')}"
        )
        self.db.add(alert)
        self.db.commit()

    def group_sources_by_type(self, sources: List[Source]) -> Dict[str, List[Source]]:
        """Группировать источники по типу.
        
        Parameters
        ----------
        sources : List[Source]
            Список источников для группировки
            
        Returns
        -------
        Dict[str, List[Source]]
            Словарь с группированными источниками по типам
        """
        grouped = {}
        for source in sources:
            if source.type not in grouped:
                grouped[source.type] = []
            grouped[source.type].append(source)
        return grouped

    def filter_sources_by_frequency(self, sources: List[Source]) -> List[Source]:
        """Фильтровать источники по частоте обновления.
        
        Parameters
        ----------
        sources : List[Source]
            Список источников для фильтрации
            
        Returns
        -------
        List[Source]
            Список источников, которые нужно обновить
        """
        now = datetime.now()
        filtered = []
        
        for source in sources:
            if not source.last_fetched:
                # Если источник никогда не обновлялся, добавляем его
                filtered.append(source)
                continue
            
            # Парсим частоту обновления
            freq_hours = self._parse_frequency(source.freq)
            if freq_hours is None:
                # Если не можем распарсить частоту, пропускаем
                continue
            
            # Проверяем, прошло ли достаточно времени с последнего обновления
            time_since_last = now - source.last_fetched
            if time_since_last >= timedelta(hours=freq_hours):
                filtered.append(source)
        
        return filtered

    def _parse_frequency(self, freq: str) -> Optional[int]:
        """Парсить частоту обновления в часах.
        
        Parameters
        ----------
        freq : str
            Строка с частотой (например, "1h", "6h", "24h")
            
        Returns
        -------
        Optional[int]
            Количество часов или None если не удалось распарсить
        """
        if freq == "instant":
            return 0
        elif freq.endswith("h"):
            try:
                return int(freq[:-1])
            except ValueError:
                return None
        else:
            return None


# Удобная функция для запуска обновления
async def update_all_regulations(db: Session) -> Dict[str, int]:
    """Обновить все регуляции из всех источников."""
    monitor = RegulationMonitorV2(db)
    return await monitor.update_all()
