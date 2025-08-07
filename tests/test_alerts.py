import pytest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from annex4parser.alerts.webhook import AlertEmitter
from tests.helpers import (
    create_test_alert_payload, assert_kafka_message_sent,
    assert_webhook_called
)


class TestAlertEmitter:
    """Тесты для системы алертов"""

    def test_init_with_webhook_only(self):
        """Тест инициализации только с webhook"""
        emitter = AlertEmitter(webhook_url="https://example.com/webhook")
        
        assert emitter.webhook_url == "https://example.com/webhook"
        assert emitter.kafka_bootstrap_servers is None
        assert emitter.kafka_topic == "rule-update"
        assert emitter.producer is None

    def test_init_with_kafka_only(self):
        """Тест инициализации только с Kafka"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer:
            mock_producer.return_value = Mock()
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")

            assert emitter.webhook_url is None
            assert emitter.kafka_bootstrap_servers == "localhost:9092"
            assert emitter.kafka_topic == "rule-update"
            assert emitter.producer is not None

    def test_init_with_both(self):
        """Тест инициализации с webhook и Kafka"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer:
            mock_producer.return_value = Mock()
            emitter = AlertEmitter(
                webhook_url="https://example.com/webhook",
                kafka_bootstrap_servers="localhost:9092"
            )
            
            assert emitter.webhook_url == "https://example.com/webhook"
            assert emitter.kafka_bootstrap_servers == "localhost:9092"
            assert emitter.kafka_topic == "rule-update"
            assert emitter.producer is not None

    def test_init_without_config(self):
        """Тест инициализации без конфигурации"""
        emitter = AlertEmitter()
        
        assert emitter.webhook_url is None
        assert emitter.kafka_bootstrap_servers is None
        assert emitter.kafka_topic == "rule-update"
        assert emitter.producer is None

    def test_emit_rule_changed_webhook_only(self, mock_session):
        """Тест отправки алерта об изменении правила через webhook"""
        emitter = AlertEmitter(webhook_url="https://example.com/webhook")
        
        payload = create_test_alert_payload()
        
        # Мокаем _send_webhook метод напрямую
        with patch.object(emitter, '_send_webhook') as mock_send_webhook:
            emitter.emit_rule_changed(
                rule_id="test_rule_123",
                severity="high",
                regulation_name="Test Regulation",
                section_code="Article1.1",
                change_type="update"
            )
            
            # Проверяем, что _send_webhook был вызван
            mock_send_webhook.assert_called_once()
            call_args = mock_send_webhook.call_args
            payload = call_args[0][0]
            assert payload["rule_id"] == "test_rule_123"
            assert payload["severity"] == "high"
            assert payload["regulation_name"] == "Test Regulation"
            assert payload["section_code"] == "Article1.1"
            assert payload["change_type"] == "update"

    def test_emit_rule_changed_kafka_only(self, mock_kafka_producer):
        """Тест отправки алерта об изменении правила через Kafka"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        emitter.emit_rule_changed(
            rule_id="test_rule_123",
            severity="high",
            regulation_name="Test Regulation",
            section_code="Article1.1",
            change_type="update"
        )
        
        # Проверяем, что сообщение было отправлено в Kafka
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "rule-update"
        
        # Проверяем payload
        payload = call_args[1]["value"]
        assert payload["rule_id"] == "test_rule_123"
        assert payload["severity"] == "high"
        assert payload["regulation_name"] == "Test Regulation"
        assert payload["section_code"] == "Article1.1"
        assert payload["change_type"] == "update"

    def test_emit_rule_changed_both_channels(self, mock_session, mock_kafka_producer):
        """Тест отправки алерта через оба канала"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(
                webhook_url="https://example.com/webhook",
                kafka_bootstrap_servers="localhost:9092"
            )
        
        # Мокаем _send_webhook метод
        with patch.object(emitter, '_send_webhook') as mock_send_webhook:
            emitter.emit_rule_changed(
                rule_id="test_rule_123",
                severity="medium",
                regulation_name="Test Regulation",
                section_code="Article2.1"
            )
            
            # Проверяем webhook
            mock_send_webhook.assert_called_once()
            
            # Проверяем Kafka
            mock_kafka_producer.send.assert_called_once()
            call_args = mock_kafka_producer.send.call_args
            assert call_args[0][0] == "rule-update"

    def test_emit_rss_update(self, mock_kafka_producer):
        """Тест отправки RSS алерта"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        emitter.emit_rss_update(
            source_id="test_rss",
            title="New AI Act Guidelines",
            link="https://example.com/guidelines",
            priority="high"
        )
        
        # Проверяем Kafka
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "rule-update"
        
        payload = call_args[1]["value"]
        assert payload["source_id"] == "test_rss"
        assert payload["title"] == "New AI Act Guidelines"
        assert payload["link"] == "https://example.com/guidelines"
        assert payload["priority"] == "high"
        assert payload["type"] == "rss_update"

    def test_emit_regulation_update(self, mock_kafka_producer):
        """Тест отправки алерта об обновлении регуляции"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        emitter.emit_regulation_update(
            regulation_id="test_reg_123",
            regulation_name="EU AI Act",
            version="2.0",
            source_url="https://example.com/regulation",
            rules_count=15
        )
        
        # Проверяем Kafka
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "rule-update"
        
        payload = call_args[1]["value"]
        assert payload["regulation_id"] == "test_reg_123"
        assert payload["regulation_name"] == "EU AI Act"
        assert payload["version"] == "2.0"
        assert payload["source_url"] == "https://example.com/regulation"
        assert payload["rules_count"] == 15
        assert payload["type"] == "regulation_update"

    def test_send_webhook_success(self, mock_session):
        """Тест успешной отправки webhook"""
        emitter = AlertEmitter(webhook_url="https://example.com/webhook")

        payload = {"test": "data"}

        # Мокаем _send_webhook метод напрямую
        with patch.object(emitter, '_send_webhook') as mock_send_webhook:
            emitter.emit_rule_changed(
                rule_id="test_rule_123",
                severity="high",
                regulation_name="Test Regulation",
                section_code="Article1.1"
            )
            
            # Проверяем, что _send_webhook был вызван
            mock_send_webhook.assert_called_once()

    def test_send_webhook_error(self, mock_session):
        """Тест ошибки при отправке webhook"""
        emitter = AlertEmitter(webhook_url="https://example.com/webhook")
        
        # Мокаем _send_webhook метод напрямую
        with patch.object(emitter, '_send_webhook') as mock_send_webhook:
            mock_send_webhook.side_effect = Exception("Network error")
            
            # Не должно вызывать исключение
            emitter.emit_rule_changed(
                rule_id="test_rule_123",
                severity="high",
                regulation_name="Test Regulation",
                section_code="Article1.1"
            )
            
            # Проверяем, что _send_webhook был вызван
            mock_send_webhook.assert_called_once()

    def test_alert_payload_structure(self):
        """Тест структуры payload алерта"""
        emitter = AlertEmitter()
        
        payload = emitter._create_alert_payload(
            alert_type="rule_changed",
            rule_id="test_rule_123",
            severity="high",
            regulation_name="Test Regulation",
            section_code="Article1.1",
            change_type="update"
        )
        
        assert "rule_id" in payload
        assert "severity" in payload
        assert "regulation_name" in payload
        assert "section_code" in payload
        assert "change_type" in payload
        assert "timestamp" in payload
        assert "source" in payload
        assert payload["source"] == "annex4parser"

    def test_alert_payload_timestamp(self):
        """Тест временной метки в payload"""
        emitter = AlertEmitter()
        
        payload = emitter._create_alert_payload(
            alert_type="rule_changed",
            rule_id="test_rule_123"
        )
        
        # Проверяем, что timestamp в правильном формате
        timestamp = payload["timestamp"]
        datetime.fromisoformat(timestamp)  # Не должно вызывать исключение

    def test_alert_payload_with_optional_fields(self):
        """Тест payload с опциональными полями"""
        emitter = AlertEmitter()
        
        payload = emitter._create_alert_payload(
            alert_type="rss_update",
            source_id="test_rss",
            title="Test Update",
            link="https://example.com/update",
            priority="medium"
        )
        
        assert payload["source_id"] == "test_rss"
        assert payload["title"] == "Test Update"
        assert payload["link"] == "https://example.com/update"
        assert payload["priority"] == "medium"


class TestAlertIntegration:
    """Тесты интеграции алертов"""

    def test_alert_with_legal_diff_analysis(self, legal_diff_analyzer, mock_kafka_producer):
        """Тест алерта с анализом правовых изменений"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        # Анализируем изменение
        old_text = "Providers may use AI systems"
        new_text = "Providers must use AI systems"
        
        change = legal_diff_analyzer.analyze_changes(old_text, new_text, "Article1.1")
        
        # Отправляем алерт на основе анализа
        emitter.emit_rule_changed(
            rule_id="rule_123",
            severity=change.severity,
            regulation_name="Test Regulation",
            section_code=change.section_code,
            change_type=change.change_type
        )
        
        # Проверяем, что алерт отправлен
        mock_kafka_producer.send.assert_called_once()
        payload = mock_kafka_producer.send.call_args[1]["value"]
        assert payload["severity"] == change.severity
        assert payload["section_code"] == change.section_code
        assert payload["change_type"] == change.change_type

    def test_multiple_alerts_same_topic(self, mock_kafka_producer):
        """Тест множественных алертов в одном топике"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        # Отправляем несколько алертов
        emitter.emit_rule_changed("rule1", "high", "Reg1", "Article1")
        emitter.emit_rss_update("rss1", "Update1", "https://example.com/1")
        emitter.emit_regulation_update("reg1", "Reg1", "1.0", "https://example.com/reg1", 10)
        
        # Проверяем, что все отправлены в один топик
        assert mock_kafka_producer.send.call_count == 3
        
        calls = mock_kafka_producer.send.call_args_list
        for call in calls:
            assert call[0][0] == "rule-update"  # Все в один топик

    def test_alert_with_different_severities(self, mock_kafka_producer):
        """Тест алертов с разными уровнями важности"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer_class.return_value = mock_kafka_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        severities = ["low", "medium", "high"]
        
        for severity in severities:
            emitter.emit_rule_changed(f"rule_{severity}", severity, "Test Reg", "Article1")
        
        # Проверяем, что все алерты отправлены
        assert mock_kafka_producer.send.call_count == 3
        
        calls = mock_kafka_producer.send.call_args_list
        for i, call in enumerate(calls):
            payload = call[1]["value"]
            assert payload["severity"] == severities[i]


class TestAlertErrorHandling:
    """Тесты обработки ошибок в алертах"""

    def test_kafka_producer_error(self):
        """Тест ошибки Kafka producer"""
        with patch('annex4parser.alerts.webhook.KafkaProducer') as mock_producer_class:
            mock_producer = Mock()
            mock_producer.send = Mock(side_effect=Exception("Kafka error"))
            mock_producer_class.return_value = mock_producer
            emitter = AlertEmitter(kafka_bootstrap_servers="localhost:9092")
        
        # Не должно вызывать исключение
        emitter.emit_rule_changed("test_rule", "high", "Test Reg", "Article1")
        
        # Проверяем, что попытка отправки была
        mock_producer.send.assert_called_once()

    def test_webhook_network_error(self, mock_session):
        """Тест сетевой ошибки webhook"""
        emitter = AlertEmitter(webhook_url="https://example.com/webhook")
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value = mock_session
            mock_session.post = AsyncMock(side_effect=Exception("Network error"))
            
            # Не должно вызывать исключение
            emitter.emit_rule_changed("test_rule", "high", "Test Reg", "Article1")

    def test_invalid_webhook_url(self):
        """Тест невалидного URL webhook"""
        emitter = AlertEmitter(webhook_url="invalid-url")
        
        # Не должно вызывать исключение
        emitter.emit_rule_changed("test_rule", "high", "Test Reg", "Article1")

    def test_missing_kafka_config(self):
        """Тест отсутствующей конфигурации Kafka"""
        emitter = AlertEmitter()  # Без конфигурации
        
        # Не должно вызывать исключение
        emitter.emit_rule_changed("test_rule", "high", "Test Reg", "Article1")
        emitter.emit_rss_update("test_rss", "Test", "https://example.com")
        emitter.emit_regulation_update("test_reg", "Test Reg", "1.0", "https://example.com", 5)
