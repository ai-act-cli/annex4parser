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

            if extra.get("consolidated") and celex_id:
                latest = await self._resolve_latest_consolidated_celex(
                    session, celex_id, endpoint
                )
                if latest:
                    celex_id = latest
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

            # Стабильная ссылка на OJ-страницу через ELI:
            # /eli/reg/{YEAR}/{NUMBER}/oj/eng для регламентов (R).
            # Если CELEX не распознаётся — откат на стандартный CELEX-страничку.
            def _stable_oj_url(celex: str) -> str:
                # CELEX консолидированных текстов: 0 + YEAR + TYPE + NUMBER + '-' + YYYYMMDD
                # Пример: 02024R1689-20241017 → базовый CELEX: 32024R1689
                m_cons = re.match(r"^0(\d{4})([A-Z])(\d+)-\d{8}$", celex, re.I)
                kind_map = {"R": "reg", "L": "dir", "D": "dec"}
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

            meta_version = eli_data.get('version') if eli_data else None
            meta_date = eli_data.get('date') if eli_data else None

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
                txt = await self._fetch_html_text(session, url)
                if not txt:
                    logger.warning("No text via HTML; skipping.")
                    return None
                title = f"Regulation {celex_id}"
                version = meta_version or (meta_date.replace("-", "") if meta_date else datetime.utcnow().strftime("%Y%m%d%H%M"))
                content_hash = hashlib.sha256(txt.encode()).hexdigest()
                has_changed = self._has_content_changed(source.id, content_hash)
                if has_changed:
                    self._ingest_regulation_text(
                        name=title,
                        version=version,
                        text=txt,
                        url=url,
                        celex_id=celex_id,
                        expression_version=meta_version,
                        work_date=meta_date,
                    )
                self._log_source_operation(source.id, "success", content_hash, len(txt.encode()), None, fetch_mode)
                return {"type": "eli_sparql", "source_id": source.id}

            # Обработка текста и метаданных
            content_hash = hashlib.sha256(txt.encode()).hexdigest()
            logger.info(f"Content hash: {content_hash[:16]}...")
            has_changed = self._has_content_changed(source.id, content_hash)
            logger.info(f"Content has changed: {has_changed}")
            name = eli_data.get('title') if eli_data else None
            name = name or f"Regulation {celex_id}"
            expr_version = meta_version
            date = meta_date
            version = (
                expr_version
                or (date.replace("-", "") if date else None)
                or datetime.utcnow().strftime("%Y%m%d%H%M")
            )
            if has_changed:
                regulation = self._ingest_regulation_text(
                    name=name,
                    version=version,
                    text=txt,
                    url=((pdf or html or {}).get("url")) or _stable_oj_url(celex_id),
                    celex_id=celex_id,
                    expression_version=expr_version,
                    work_date=date,
                )
                logger.info(f"Updated regulation from SPARQL source {source.id}: {regulation.name}")
            else:
                logger.info("No changes detected, skipping regulation update")
            self._log_source_operation(source.id, "success", content_hash, len(txt.encode()), None, fetch_mode)
            return {"type": "eli_sparql", "source_id": source.id}
        except aiohttp.ClientResponseError as e:
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
                        source.id, "success", content_hash, None, None
                    )

            # Логируем сам факт обновления фида
            self._log_source_operation(
                source.id,
                "success",
                hashlib.sha256(str(entries).encode()).hexdigest(),
                len(str(entries)),
                None,
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
            self._log_source_operation(source.id, "error", None, None, str(e))
            return None
    
    async def _process_html_source(
        self, 
        source: Source, 
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать HTML источник (fallback)."""
        try:
            text = await self._fetch_html_text(session, source.url)
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            has_changed = self._has_content_changed(source.id, content_hash)
            celex_id = self._extract_celex_id(source.url) or "UNKNOWN"
            name = f"Regulation {celex_id}"
            if has_changed:
                regulation = self._ingest_regulation_text(
                    name=name,
                    version=datetime.utcnow().strftime("%Y%m%d%H%M"),
                    text=text,
                    url=source.url,
                    celex_id=celex_id
                )
                logger.info(f"Updated regulation from HTML source {source.id}")
            self._log_source_operation(
                source.id, "success", content_hash, len(text), None, "html"
            )
            
            return {"type": "html", "source_id": source.id}
            
        except aiohttp.ClientResponseError as e:
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
    ) -> Optional[str]:
        """Найти последний консолидированный CELEX для базового идентификатора."""
        query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?celex ?date WHERE {{
          ?w cdm:resource_legal_id_celex ?celex .
        FILTER(STRSTARTS(?celex, CONCAT('0', SUBSTR('{base_celex}',2), '-')))
          OPTIONAL {{ ?w cdm:work_date_document ?date }}
        }} ORDER BY DESC(?date) DESC(?celex) LIMIT 1
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
                timeout=aiohttp.ClientTimeout(total=30),
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
        return rows[0]["celex"]["value"] if rows else None

    async def _fetch_html_text(self, session: aiohttp.ClientSession, url: str) -> str:
        """Получить текст из HTML-страницы с уважением к robots.txt."""
        from .ethical_fetcher import ethical_fetch

        try:
            html = await ethical_fetch(session, url, user_agent=UA)
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
        from .regulation_monitor import parse_rules, canonicalize, format_order_index
        from .legal_diff import LegalDiffAnalyzer
        
        # Проверяем, есть ли уже регуляция с таким CELEX ID
        existing_regulation = (
            self.db.query(Regulation)
            .filter_by(celex_id=celex_id)
            .order_by(Regulation.last_updated.desc())
            .first()
        )
        
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

        if existing_regulation:
            # Обновляем существующую регуляцию
            regulation = existing_regulation
            regulation.version = version
            regulation.expression_version = expression_version
            regulation.work_date = work_date_dt
            if work_date_dt:
                regulation.effective_date = work_date_dt
            regulation.last_updated = datetime.utcnow()
            regulation.source_url = url
        else:
            # Создаём новую регуляцию
            regulation = Regulation(
                name=name,
                celex_id=celex_id,
                version=version,
                expression_version=expression_version,
                work_date=work_date_dt,
                source_url=url,
                effective_date=work_date_dt or datetime.utcnow(),
                last_updated=datetime.utcnow(),
                status="active"
            )
            self.db.add(regulation)
        
        self.db.flush()


        # Парсим правила и формируем карту существующих секций
        rules_data = parse_rules(text)
        logger.info("Parsed rules: %d", len(rules_data))
        analyzer = LegalDiffAnalyzer()

        existing_rules = (
            self.db.query(Rule)
            .filter_by(regulation_id=regulation.id)
            .all()
        )
        code_to_rule: Dict[str, Rule] = {}
        for r in existing_rules:
            canon = canonicalize(r.section_code)
            if r.section_code != canon:
                r.section_code = canon
            code_to_rule[canon] = r

        for rule_data in rules_data:
            section_code = canonicalize(rule_data["section_code"])
            parent_code = canonicalize(rule_data.get("parent_section_code")) if rule_data.get("parent_section_code") else None

            existing_rule = code_to_rule.get(section_code)
            if not existing_rule:
                existing_rule = (
                    self.db.query(Rule)
                    .filter_by(regulation_id=regulation.id, section_code=section_code)
                    .first()
                )
                if existing_rule:
                    code_to_rule[section_code] = existing_rule

            if existing_rule:
                change = analyzer.analyze_changes(
                    existing_rule.content or "",
                    rule_data["content"],
                    section_code,
                )

                existing_rule.content = rule_data["content"]
                t = (rule_data["title"] or "").strip()
                existing_rule.title = t or None
                existing_rule.version = version
                existing_rule.risk_level = infer_risk_level(section_code, rule_data["content"])
                if rule_data.get("order_index") is not None:
                    existing_rule.order_index = format_order_index(rule_data["order_index"])
                if work_date_dt:
                    existing_rule.effective_date = work_date_dt
                if change.change_type != "no_change":
                    existing_rule.last_modified = work_date_dt or datetime.utcnow()
                existing_rule.ingested_at = datetime.utcnow()
                old_code = existing_rule.section_code
                if old_code != section_code:
                    existing_rule.section_code = section_code
                    if old_code in code_to_rule:
                        del code_to_rule[old_code]
                    code_to_rule[section_code] = existing_rule
                    self._relink_children(existing_rule, old_code, section_code, code_to_rule)
                else:
                    existing_rule.section_code = section_code
                    code_to_rule[section_code] = existing_rule

                if parent_code and existing_rule.parent_rule_id is None:
                    parent = code_to_rule.get(parent_code)
                    if not parent:
                        parent = (
                            self.db.query(Rule)
                            .filter_by(regulation_id=regulation.id, section_code=parent_code)
                            .first()
                        )
                        if parent:
                            code_to_rule[parent_code] = parent
                    if parent:
                        existing_rule.parent_rule_id = parent.id

                if change.severity in ["high", "critical", "major"]:
                    prio = "urgent" if change.severity in ["high", "critical", "major"] else "medium"
                    alert = ComplianceAlert(
                        rule_id=existing_rule.id,
                        alert_type="rule_updated",
                        priority=prio,
                        message=f"Rule {section_code} updated: {change.change_type} - {analyzer.get_change_summary(change)}",
                    )
                    self.db.add(alert)

                    mappings = (
                        self.db.query(DocumentRuleMapping)
                        .filter_by(rule_id=existing_rule.id)
                        .all()
                    )

                    for mapping in mappings:
                        doc = self.db.get(Document, mapping.document_id)
                        if doc:
                            doc.compliance_status = "outdated"
                            doc.last_modified = datetime.utcnow()
                            doc_alert = ComplianceAlert(
                                document_id=doc.id,
                                rule_id=existing_rule.id,
                                alert_type="document_outdated",
                                priority="high",
                                message=f"Document {doc.filename or doc.id} outdated due to changes in {section_code}",
                            )
                            self.db.add(doc_alert)
            else:
                parent_id = None
                if parent_code:
                    parent = code_to_rule.get(parent_code)
                    if not parent:
                        parent = (
                            self.db.query(Rule)
                            .filter_by(regulation_id=regulation.id, section_code=parent_code)
                            .first()
                        )
                        if parent:
                            code_to_rule[parent_code] = parent
                    parent_id = parent.id if parent else None

                t = (rule_data["title"] or "").strip()
                rule = Rule(
                    regulation_id=regulation.id,
                    section_code=section_code,
                    title=(t or None),
                    content=rule_data["content"],
                    risk_level=infer_risk_level(section_code, rule_data["content"]),
                    version=version,
                    effective_date=work_date_dt,
                    last_modified=work_date_dt or datetime.utcnow(),
                    parent_rule_id=parent_id,
                    order_index=format_order_index(rule_data.get("order_index")) if rule_data.get("order_index") is not None else None,
                    ingested_at=datetime.utcnow(),
                )
                self.db.add(rule)
                self.db.flush()
                code_to_rule[section_code] = rule

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
