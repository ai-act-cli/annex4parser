# alerts/webhook.py
"""Event-driven алерты с поддержкой webhook и Kafka.

Этот модуль предоставляет систему алертов для уведомления о изменениях
в регуляторных документах через webhook и Kafka topics.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any
import aiohttp
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class AlertEmitter:
    """Эмиттер алертов с поддержкой webhook и Kafka."""
    
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        kafka_bootstrap_servers: Optional[str] = None,
        kafka_topic: str = "rule-update"
    ):
        self.webhook_url = webhook_url
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topic = kafka_topic
        
        # Инициализируем Kafka producer если указаны серверы
        self.kafka_producer = None
        if kafka_bootstrap_servers:
            try:
                self.kafka_producer = KafkaProducer(
                    bootstrap_servers=kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None
                )
                logger.info(f"Kafka producer initialized for topic: {kafka_topic}")
            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {e}")
                self.kafka_producer = None
        
        # Алиас для совместимости с тестами
        self.producer = self.kafka_producer
    
    def emit_rule_changed(
        self, 
        rule_id: str, 
        severity: str,
        regulation_name: str,
        section_code: str,
        change_type: str = "update"
    ):
        """Эмитировать алерт об изменении правила.
        
        Parameters
        ----------
        rule_id : str
            ID правила
        severity : str
            Серьёзность изменения (major, minor, clarification)
        regulation_name : str
            Название регуляции
        section_code : str
            Код секции (например, "Article11")
        change_type : str
            Тип изменения (update, new, deleted)
        """
        payload = {
            "rule_id": rule_id,
            "severity": severity,
            "regulation_name": regulation_name,
            "section_code": section_code,
            "change_type": change_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "annex4parser"
        }
        
        # Отправляем в Kafka
        if self.kafka_producer:
            try:
                future = self.kafka_producer.send(
                    self.kafka_topic, 
                    value=payload,
                    key=rule_id
                )
                # Асинхронная отправка
                future.add_callback(self._on_kafka_send_success)
                future.add_errback(self._on_kafka_send_error)
                logger.debug(f"Kafka message sent for rule {rule_id}")
            except Exception as e:
                logger.error(f"Failed to send Kafka message: {e}")
        
        # Отправляем webhook
        if self.webhook_url:
            self._send_webhook_safe(payload)
    
    def emit_rss_update(
        self, 
        source_id: str, 
        title: str, 
        link: str,
        priority: str = "medium"
    ):
        """Эмитировать алерт о новом RSS-элементе."""
        payload = {
            "source_id": source_id,
            "title": title,
            "link": link,
            "priority": priority,
            "type": "rss_update",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "annex4parser"
        }
        
        # Отправляем в Kafka
        if self.kafka_producer:
            try:
                future = self.kafka_producer.send(
                    self.kafka_topic,
                    value=payload,
                    key=source_id
                )
                future.add_callback(self._on_kafka_send_success)
                future.add_errback(self._on_kafka_send_error)
            except Exception as e:
                logger.error(f"Failed to send RSS Kafka message: {e}")
        
        # Отправляем webhook
        if self.webhook_url:
            self._send_webhook_safe(payload)
    
    def emit_regulation_update(
        self,
        regulation_id: str,
        regulation_name: str,
        version: str,
        source_url: str,
        rules_count: int
    ):
        """Эмитировать алерт об обновлении регуляции."""
        payload = {
            "regulation_id": regulation_id,
            "regulation_name": regulation_name,
            "version": version,
            "source_url": source_url,
            "rules_count": rules_count,
            "type": "regulation_update",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "annex4parser"
        }
        
        # Отправляем в Kafka
        if self.kafka_producer:
            try:
                future = self.kafka_producer.send(
                    self.kafka_topic,
                    value=payload,
                    key=regulation_id
                )
                future.add_callback(self._on_kafka_send_success)
                future.add_errback(self._on_kafka_send_error)
            except Exception as e:
                logger.error(f"Failed to send regulation Kafka message: {e}")
        
        # Отправляем webhook
        if self.webhook_url:
            self._send_webhook_safe(payload)
    
    def _send_webhook_safe(self, payload: Dict[str, Any]):
        """Безопасная отправка webhook с обработкой event loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если loop уже запущен, создаем задачу
                asyncio.create_task(self._send_webhook(payload))
            else:
                # Если loop не запущен, запускаем его
                loop.run_until_complete(self._send_webhook(payload))
        except RuntimeError:
            # Если нет event loop вообще, создаем новый
            asyncio.run(self._send_webhook(payload))
        except Exception as e:
            logger.error(f"Failed to send webhook safely: {e}")

    async def _send_webhook(self, payload: Dict[str, Any]):
        """Отправить webhook асинхронно."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status >= 400:
                        logger.error(f"Webhook failed with status {resp.status}")
                    else:
                        logger.debug(f"Webhook sent successfully")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
    
    def _on_kafka_send_success(self, record_metadata):
        """Callback для успешной отправки в Kafka."""
        logger.debug(
            f"Kafka message sent to {record_metadata.topic} "
            f"partition {record_metadata.partition} "
            f"offset {record_metadata.offset}"
        )
    
    def _on_kafka_send_error(self, exc):
        """Callback для ошибки отправки в Kafka."""
        logger.error(f"Kafka send error: {exc}")
    
    def close(self):
        """Закрыть соединения."""
        if self.kafka_producer:
            self.kafka_producer.close()
    
    def _create_alert_payload(self, alert_type: str, **kwargs) -> Dict[str, Any]:
        """Создает базовый payload для алерта."""
        payload = {
            "alert_type": alert_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "annex4parser"
        }
        payload.update(kwargs)
        return payload


# Глобальный экземпляр эмиттера
_alert_emitter: Optional[AlertEmitter] = None


def get_alert_emitter(
    webhook_url: Optional[str] = None,
    kafka_bootstrap_servers: Optional[str] = None,
    kafka_topic: str = "rule-update"
) -> AlertEmitter:
    """Получить глобальный экземпляр AlertEmitter."""
    global _alert_emitter
    if _alert_emitter is None:
        _alert_emitter = AlertEmitter(
            webhook_url=webhook_url,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kafka_topic=kafka_topic
        )
    return _alert_emitter


# Удобные функции для эмиссии алертов
def emit_rule_changed(rule_id: str, severity: str, **kwargs):
    """Эмитировать алерт об изменении правила."""
    emitter = get_alert_emitter()
    emitter.emit_rule_changed(rule_id, severity, **kwargs)


def emit_rss_update(source_id: str, title: str, link: str, **kwargs):
    """Эмитировать алерт о новом RSS-элементе."""
    emitter = get_alert_emitter()
    emitter.emit_rss_update(source_id, title, link, **kwargs)


def emit_regulation_update(regulation_id: str, regulation_name: str, **kwargs):
    """Эмитировать алерт об обновлении регуляции."""
    emitter = get_alert_emitter()
    emitter.emit_regulation_update(regulation_id, regulation_name, **kwargs)


# Примеры использования
if __name__ == "__main__":
    import asyncio
    
    async def test_alerts():
        # Инициализируем эмиттер
        emitter = AlertEmitter(
            webhook_url="https://your-webhook-url.com/notify",
            kafka_bootstrap_servers="localhost:9092"
        )
        
        # Эмитируем тестовые алерты
        emitter.emit_rule_changed(
            rule_id="rule-123",
            severity="major",
            regulation_name="EU AI Act",
            section_code="Article11"
        )
        
        emitter.emit_rss_update(
            source_id="ep_plenary",
            title="New AI Regulation Published",
            link="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1234"
        )
        
        # Ждём отправки webhook
        await asyncio.sleep(1)
        emitter.close()
    
    asyncio.run(test_alerts())
