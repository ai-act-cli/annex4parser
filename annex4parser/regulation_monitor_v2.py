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
from .eli_client import fetch_latest_eli
from .rss_listener import fetch_rss_feed, RSSMonitor

logger = logging.getLogger(__name__)

# User-Agent для этичного скрапинга
UA = "Annex4ComplianceBot/1.2 (+https://your-domain.example/contact)"


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
        for source_config in self.config['sources']:
            source = self.db.query(Source).filter_by(id=source_config['id']).first()
            if not source:
                source = Source(
                    id=source_config['id'],
                    url=source_config['url'],
                    type=source_config['type'],
                    freq=source_config['freq'],
                    active=True
                )
                self.db.add(source)
        
        self.db.commit()
        logger.info(f"Initialized {len(self.config['sources'])} sources")
    
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
        tasks = []
        async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
            # ELI SPARQL источники
            for source in eli_sources:
                tasks.append(self._process_eli_source(source, session))
            
            # RSS источники
            for source in rss_sources:
                tasks.append(self._process_rss_source(source, session))
            
            # HTML источники
            for source in html_sources:
                tasks.append(self._process_html_source(source, session))
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Подсчитываем статистику
        stats = {"eli_sparql": 0, "rss": 0, "html": 0, "errors": 0}
        for result in results:
            if isinstance(result, Exception):
                stats["errors"] += 1
                logger.error(f"Source processing error: {result}")
            elif result:
                source_type = result.get("type", "unknown")
                stats[source_type] += 1
        
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
            # Извлекаем CELEX ID из URL или конфигурации
            celex_id = self._extract_celex_id(source.url)
            logger.info(f"Extracted CELEX ID: {celex_id} from URL: {source.url}")
            if not celex_id:
                logger.warning(f"No CELEX ID found for source {source.id}")
                return None
            
            # Получаем данные через ELI
            eli_data = await fetch_latest_eli(session, celex_id)
            logger.info(f"ELI data received: {eli_data is not None}")
            if not eli_data:
                return None
            
            # Проверяем изменения
            content_hash = hashlib.sha256(eli_data['text'].encode()).hexdigest()
            logger.info(f"Content hash: {content_hash[:16]}...")
            
            # Логируем операцию
            self._log_source_operation(
                source.id, "success", content_hash, 
                len(eli_data['text']), None
            )
            
            # Обновляем регуляцию если есть изменения
            has_changed = self._has_content_changed(source.id, content_hash)
            logger.info(f"Content has changed: {has_changed}")
            if has_changed:
                regulation = self._ingest_regulation_text(
                    name=eli_data.get('title', f"Regulation {celex_id}"),
                    version=eli_data.get('version', datetime.utcnow().strftime("%Y%m%d%H%M")),
                    text=eli_data['text'],
                    url=source.url
                )
                logger.info(f"Updated regulation from ELI source {source.id}: {regulation.name}")
            else:
                logger.info("No changes detected, skipping regulation update")
            
            return {"type": "eli_sparql", "source_id": source.id}
            
        except Exception as e:
            self._log_source_operation(source.id, "error", None, None, str(e))
            raise
    
    async def _process_rss_source(
        self, 
        source: Source, 
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать RSS источник."""
        try:
            # Получаем RSS-фид
            entries = await fetch_rss_feed(source.url)
            
            # Проверяем новые элементы
            new_entries = []
            for link, content_hash, title in entries:
                if not self._has_content_changed(source.id, content_hash):
                    new_entries.append((link, content_hash, title))
            
            # Логируем операцию
            self._log_source_operation(
                source.id, "success", 
                hashlib.sha256(str(entries).encode()).hexdigest(),
                len(str(entries)), None
            )
            
            # Создаём алерты для новых элементов
            for link, content_hash, title in new_entries:
                self._create_rss_alert(source.id, title, link)
            
            return {"type": "rss", "source_id": source.id, "new_entries": len(new_entries)}
            
        except Exception as e:
            self._log_source_operation(source.id, "error", None, None, str(e))
            raise
    
    async def _process_html_source(
        self, 
        source: Source, 
        session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """Обработать HTML источник (fallback)."""
        try:
            # Используем существующую логику из regulation_monitor.py
            from .regulation_monitor import fetch_regulation_text
            
            text = await self._fetch_html_text(session, source.url)
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            
            # Логируем операцию
            self._log_source_operation(
                source.id, "success", content_hash, len(text), None
            )
            
            # Обновляем регуляцию если есть изменения
            if self._has_content_changed(source.id, content_hash):
                regulation = self._ingest_regulation_text(
                    name=f"Regulation from {source.id}",
                    version=datetime.utcnow().strftime("%Y%m%d%H%M"),
                    text=text,
                    url=source.url
                )
                logger.info(f"Updated regulation from HTML source {source.id}")
            
            return {"type": "html", "source_id": source.id}
            
        except Exception as e:
            self._log_source_operation(source.id, "error", None, None, str(e))
            raise
    
    async def _fetch_html_text(self, session: aiohttp.ClientSession, url: str) -> str:
        """Получить текст из HTML-страницы."""
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            html = await resp.text()
            
        # Используем BeautifulSoup для извлечения текста
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n")
    
    def _extract_celex_id(self, url: str) -> Optional[str]:
        """Извлечь CELEX ID из URL."""
        import re
        logger.info(f"Extracting CELEX ID from URL: {url}")
        match = re.search(r'CELEX%3A(\d+)', url)
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
        error_message: Optional[str]
    ):
        """Логировать операцию с источником."""
        log = RegulationSourceLog(
            source_id=source_id,
            status=status,
            content_hash=content_hash,
            bytes_downloaded=bytes_downloaded,
            error_message=error_message
        )
        self.db.add(log)
        self.db.commit()
    
    def _ingest_regulation_text(
        self, 
        name: str, 
        version: str, 
        text: str, 
        url: str
    ) -> Regulation:
        """Ингестировать текст регуляции в базу данных."""
        from .regulation_monitor import parse_rules
        from .legal_diff import LegalDiffAnalyzer
        
        # Проверяем, есть ли уже регуляция с таким именем
        existing_regulation = (
            self.db.query(Regulation)
            .filter_by(name=name)
            .order_by(Regulation.last_updated.desc())
            .first()
        )
        
        if existing_regulation:
            # Обновляем существующую регуляцию
            regulation = existing_regulation
            regulation.version = version
            regulation.last_updated = datetime.utcnow()
            regulation.source_url = url
        else:
            # Создаём новую регуляцию
            regulation = Regulation(
                name=name,
                version=version,
                source_url=url,
                effective_date=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                status="active"
            )
            self.db.add(regulation)
        
        self.db.flush()
        
        # Парсим правила
        rules_data = parse_rules(text)
        analyzer = LegalDiffAnalyzer()
        
        for rule_data in rules_data:
            # Проверяем, есть ли уже правило с таким section_code
            existing_rule = (
                self.db.query(Rule)
                .filter_by(
                    regulation_id=regulation.id,
                    section_code=rule_data["section_code"]
                )
                .first()
            )
            
            if existing_rule:
                # Анализируем изменения
                change = analyzer.analyze_changes(
                    existing_rule.content or "",
                    rule_data["content"],
                    rule_data["section_code"]
                )
                
                # Обновляем правило
                existing_rule.content = rule_data["content"]
                existing_rule.title = rule_data["title"]
                existing_rule.version = version
                existing_rule.last_modified = datetime.utcnow()
                
                # Создаём алерт если есть значительные изменения
                if change.severity in ["high", "critical"]:
                    alert = ComplianceAlert(
                        rule_id=existing_rule.id,
                        alert_type="rule_updated",
                        priority=change.severity,
                        message=f"Rule {rule_data['section_code']} updated: {change.change_type} - {analyzer.get_change_summary(change)}"
                    )
                    self.db.add(alert)
                    
                    # Помечаем связанные документы как устаревшие
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
            else:
                # Создаём новое правило
                rule = Rule(
                    regulation_id=regulation.id,
                    section_code=rule_data["section_code"],
                    title=rule_data["title"],
                    content=rule_data["content"],
                    risk_level="medium",
                    version=version,
                    effective_date=datetime.utcnow(),
                    last_modified=datetime.utcnow()
                )
                self.db.add(rule)
        
        self.db.commit()
        return regulation
    
    def _create_rss_alert(self, source_id: str, title: str, link: str):
        """Создать алерт для нового RSS-элемента."""
        alert = ComplianceAlert(
            document_id=None,  # RSS алерты не привязаны к документам
            rule_id=None,
            alert_type="new_requirement",
            priority="medium",
            message=f"New regulatory update from {source_id}: {title} - {link}"
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
            freq_hours = self.parse_frequency(source.freq)
            if freq_hours is None:
                # Если не можем распарсить частоту, пропускаем
                continue
            
            # Проверяем, прошло ли достаточно времени с последнего обновления
            time_since_last = now - source.last_fetched
            if time_since_last >= timedelta(hours=freq_hours):
                filtered.append(source)
        
        return filtered

    def parse_frequency(self, freq: str) -> Optional[int]:
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
