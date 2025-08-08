# Production Deployment Guide

Руководство по развертыванию Annex4Parser в production-среде с поддержкой всех новых компонентов.

## 🏗️ Архитектура

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   RSS Sources   │    │  ELI SPARQL     │    │  HTML Sources   │
│   (EUR-Lex,     │    │  (EUR-Lex API)  │    │  (Fallback)     │
│    EP, EC)      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │ Regulation      │
                    │ Monitor V2      │
                    │ (Async)         │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │ Legal Diff      │
                    │ Analyzer        │
                    └─────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kafka Topic   │    │   Webhook       │    │   Database      │
│   rule-update   │    │   Notifications │    │   (PostgreSQL)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Требования

### Системные требования
- Python 3.8+
- PostgreSQL 12+
- Kafka 2.8+ (опционально)
- Redis (для кеширования, опционально)

### Зависимости
```bash
pip install -r requirements.txt
```

## 🚀 Быстрый старт

### 1. Настройка базы данных

```bash
# Создаём PostgreSQL базу данных
createdb compliance_production

# Применяем миграции
python -m alembic upgrade head
```

### 2. Настройка конфигурации

Создайте файл `.env`:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost/compliance_production

# Kafka (опционально)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=rule-update

# Webhook (опционально)
WEBHOOK_URL=https://your-domain.com/webhook

# Monitoring
LOG_LEVEL=INFO
CACHE_TTL=3600
```

### 3. Запуск мониторинга

```python
import asyncio
from annex4parser.regulation_monitor_v2 import update_all_regulations
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Подключаемся к БД
engine = create_engine("postgresql://user:password@localhost/compliance_production")
Session = sessionmaker(bind=engine)

async def run_monitoring():
    with Session() as session:
        stats = await update_all_regulations(session)
        print(f"Monitoring completed: {stats}")

# Запускаем
asyncio.run(run_monitoring())
```

## 🔧 Production настройки

### 1. Docker Compose

Создайте `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: compliance_production
      POSTGRES_USER: compliance_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  kafka:
    image: confluentinc/cp-kafka:7.0.0
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    ports:
      - "9092:9092"

  zookeeper:
    image: confluentinc/cp-zookeeper:7.0.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  redis:
    image: redis:6-alpine
    ports:
      - "6379:6379"

  annex4parser:
    build: .
    depends_on:
      - postgres
      - kafka
      - redis
    environment:
      - DATABASE_URL=postgresql://compliance_user:secure_password@postgres/compliance_production
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./logs:/app/logs
      - ./cache:/app/cache

volumes:
  postgres_data:
```

### 2. Dockerfile

Создайте `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY annex4parser/ ./annex4parser/
COPY examples/ ./examples/
COPY tests/ ./tests/

# Создаём пользователя
RUN useradd -m -u 1000 annex4parser
USER annex4parser

# Запускаем мониторинг
CMD ["python", "-m", "annex4parser.regulation_monitor_v2"]
```

### 3. Systemd Service

Создайте `/etc/systemd/system/annex4parser.service`:

```ini
[Unit]
Description=Annex4Parser Regulatory Monitor
After=network.target postgresql.service

[Service]
Type=simple
User=annex4parser
WorkingDirectory=/opt/annex4parser
Environment=PATH=/opt/annex4parser/venv/bin
ExecStart=/opt/annex4parser/venv/bin/python -m annex4parser.regulation_monitor_v2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 📊 Мониторинг и логирование

### 1. Логирование

```python
import logging
from logging.handlers import RotatingFileHandler

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('/var/log/annex4parser/app.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
```

### 2. Метрики

```python
from prometheus_client import Counter, Histogram, start_http_server

# Метрики
REGULATION_UPDATES = Counter('regulation_updates_total', 'Total regulation updates')
RSS_ENTRIES = Counter('rss_entries_total', 'Total RSS entries processed')
ELI_REQUESTS = Counter('eli_requests_total', 'Total ELI SPARQL requests')
PROCESSING_TIME = Histogram('processing_time_seconds', 'Time spent processing updates')

# Запускаем HTTP сервер для метрик
start_http_server(8000)
```

### 3. Health Checks

```python
from flask import Flask, jsonify
import psycopg2
from datetime import datetime
import json

app = Flask(__name__)

# Assuming DATABASE_URL is defined elsewhere or passed as an environment variable
# For this example, we'll use a placeholder.
DATABASE_URL = "postgresql://user:password@localhost/compliance_production"
SECRET_KEY = "your-secret-key" # Placeholder for SECRET_KEY

@app.route('/health')
def health_check():
    try:
        # Проверяем подключение к БД
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 🔒 Безопасность

### 1. Сетевая безопасность

```bash
# Firewall правила
sudo ufw allow 5432/tcp  # PostgreSQL
sudo ufw allow 9092/tcp  # Kafka
sudo ufw allow 8080/tcp  # Health check
sudo ufw deny 22/tcp      # Отключаем SSH
```

### 2. SSL/TLS

```python
# SSL конфигурация для PostgreSQL
DATABASE_URL = "postgresql://user:password@localhost/compliance_production?sslmode=require"

# SSL для Kafka
KAFKA_SSL_CONFIG = {
    'security_protocol': 'SSL',
    'ssl_cafile': '/path/to/ca.pem',
    'ssl_certfile': '/path/to/cert.pem',
    'ssl_keyfile': '/path/to/key.pem'
}
```

### 3. Аутентификация

```python
# JWT токены для API
import jwt
from functools import wraps
from flask import request, jsonify

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "No token provided"}), 401
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user = payload
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        
        return f(*args, **kwargs)
    return decorated
```

## 📈 Масштабирование

### 1. Горизонтальное масштабирование

```yaml
# docker-compose.scale.yml
services:
  annex4parser:
    deploy:
      replicas: 3
    environment:
      - INSTANCE_ID=${HOSTNAME}
```

### 2. Load Balancing

```nginx
# nginx.conf
upstream annex4parser {
    server annex4parser1:8080;
    server annex4parser2:8080;
    server annex4parser3:8080;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://annex4parser;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Кеширование

```python
import redis
from functools import lru_cache

# Redis кеш
REDIS_URL = "redis://localhost:6379/0" # Placeholder for REDIS_URL

redis_client = redis.Redis.from_url(REDIS_URL)

@lru_cache(maxsize=1000)
def cached_regulation_fetch(celex_id: str):
    # Проверяем кеш
    cached = redis_client.get(f"regulation:{celex_id}")
    if cached:
        return json.loads(cached)
    
    # Фетчим из источника
    # Assuming fetch_regulation_by_celex is defined elsewhere or will be added
    # For this example, we'll just return a placeholder
    result = {"celex_id": celex_id, "title": "Placeholder Regulation", "url": "https://example.com"}
    
    # Сохраняем в кеш
    redis_client.setex(f"regulation:{celex_id}", 3600, json.dumps(result))
    
    return result
```

## 🚨 Troubleshooting

### 1. Проблемы с подключением к БД

```bash
# Проверяем подключение
psql -h localhost -U compliance_user -d compliance_production

# Проверяем логи
tail -f /var/log/postgresql/postgresql-13-main.log
```

### 2. Проблемы с Kafka

```bash
# Проверяем статус Kafka
kafka-topics --bootstrap-server localhost:9092 --list

# Проверяем сообщения
kafka-console-consumer --bootstrap-server localhost:9092 --topic rule-update --from-beginning
```

### 3. Проблемы с мониторингом

```python
# Тестовый скрипт
import asyncio
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Source # Assuming Source model is needed for this example

# Подключаемся к БД
engine = create_engine("postgresql://user:password@localhost/compliance_production")
Session = sessionmaker(bind=engine)

async def debug_monitoring():
    with Session() as session:
        monitor = RegulationMonitorV2(session)
        
        # Проверяем источники
        sources = session.query(Source).all()
        print(f"Active sources: {len(sources)}")
        
        # Тестируем один источник
        if sources:
            source = sources[0]
            print(f"Testing source: {source.id}")
            # ... тестирование

asyncio.run(debug_monitoring())
```

## 📚 Дополнительные ресурсы

- [EUR-Lex API Documentation](https://eur-lex.europa.eu/eli-register/technical_information.html)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Prometheus Monitoring](https://prometheus.io/docs/)

---

**Annex4Parser Production Deployment** - готов к работе! 🚀
