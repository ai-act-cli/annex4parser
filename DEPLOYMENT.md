# Annex4Parser Deployment Guide

This guide will help you deploy Annex4Parser in production for analyzing document compliance with EU AI Act requirements.

## 🏗️ System Architecture

### Components

- **Document Ingestion** - Document loading and parsing
- **Compliance Mapping** - Mapping with regulatory rules
- **Regulation Monitor** - Monitoring regulatory updates
- **Database Layer** - SQLAlchemy + SQLite/PostgreSQL
- **API Layer** - FastAPI (optional)

### Infrastructure Requirements

- **CPU**: 2+ cores
- **RAM**: 4GB+ (8GB for large documents)
- **Storage**: 10GB+ for documents and database
- **Network**: Stable internet connection

## 🚀 Deployment

### Option 1: Local Deployment

#### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd a4p

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

#### 2. Database Setup

```python
# Create production database
from sqlalchemy import create_engine
from annex4parser.models import Base

# SQLite (for small projects)
engine = create_engine("sqlite:///production_compliance.db")

# PostgreSQL (for large projects)
# engine = create_engine("postgresql://user:pass@localhost/compliance_db")

Base.metadata.create_all(engine)
```

#### 3. Load Regulations

```python
from annex4parser.regulation_monitor import RegulationMonitor
from sqlalchemy.orm import sessionmaker

Session = sessionmaker(bind=engine)

with Session() as session:
    monitor = RegulationMonitor(session)
    
    # Load EU AI Act
    regulation = monitor.update(
        name="EU AI Act",
        version="2024.1",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R0988"
    )
    
    print(f"Loaded {len(regulation.rules)} rules")
```

### Option 2: Docker Deployment

#### 1. Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt .
COPY annex4parser/ ./annex4parser/
COPY tests/ ./tests/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create documents directory
RUN mkdir -p /app/documents

# Create user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Start application
CMD ["python", "-m", "annex4parser"]
```

#### 2. Create docker-compose.yml

```yaml
version: '3.8'

services:
  annex4parser:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./documents:/app/documents
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///data/compliance.db
      - CACHE_DIR=/app/cache
    restart: unless-stopped

  # PostgreSQL (optional)
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: compliance_db
      POSTGRES_USER: annex4user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

#### 3. Launch

```bash
# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f annex4parser
```

### Option 3: Cloud Deployment

#### AWS EC2

```bash
# Connect to server
ssh -i key.pem ubuntu@your-server-ip

# Install dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv git

# Clone project
git clone <repository-url>
cd a4p

# Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run as service
sudo systemctl enable annex4parser
sudo systemctl start annex4parser
```

#### Google Cloud Run

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/annex4parser', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/annex4parser']
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'annex4parser'
      - '--image'
      - 'gcr.io/$PROJECT_ID/annex4parser'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
```

## 🔧 Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///production_compliance.db
# or
DATABASE_URL=postgresql://user:pass@localhost/compliance_db

# Caching
CACHE_DIR=/app/cache
CACHE_TTL=3600

# Logging
LOG_LEVEL=INFO
LOG_FILE=/app/logs/annex4parser.log

# Security
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1

# Performance
MAX_WORKERS=4
CHUNK_SIZE=1000
```

### Configuration File

```python
# config.py
import os
from pathlib import Path

class Config:
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///compliance.db')
    
    # Caching
    CACHE_DIR = Path(os.getenv('CACHE_DIR', './cache'))
    CACHE_TTL = int(os.getenv('CACHE_TTL', 3600))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', './logs/annex4parser.log')
    
    # Performance
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', 4))
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 1000))
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')
```

## 📊 Monitoring

### Logging

```python
import logging
from logging.handlers import RotatingFileHandler

# Setup logging
def setup_logging():
    logger = logging.getLogger('annex4parser')
    logger.setLevel(logging.INFO)
    
    # File handler
    file_handler = RotatingFileHandler(
        'logs/annex4parser.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    logger.addHandler(console_handler)
    
    return logger
```

### Metrics

```python
import time
from functools import wraps

def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        # Log metrics
        logger.info(f"{func.__name__} executed in {execution_time:.2f}s")
        
        return result
    return wrapper

# Usage
@monitor_performance
def analyze_document(file_path, session):
    # Document analysis
    pass
```

### Health Check

```python
def health_check():
    """System health check"""
    try:
        # Database check
        session = Session()
        rules_count = session.query(Rule).count()
        session.close()
        
        # Cache check
        cache_dir = Path("./cache")
        cache_accessible = cache_dir.exists() and cache_dir.is_dir()
        
        return {
            "status": "healthy",
            "database": "connected",
            "rules_count": rules_count,
            "cache": "accessible" if cache_accessible else "error"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
```

## 🔒 Security

### Authentication

```python
from functools import wraps
import jwt

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return {"error": "No token provided"}, 401
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user = payload
        except jwt.InvalidTokenError:
            return {"error": "Invalid token"}, 401
        
        return f(*args, **kwargs)
    return decorated_function
```

### File Validation

```python
import magic
from pathlib import Path

ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc'}
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
}

def validate_file(file_path):
    """Validate uploaded file"""
    path = Path(file_path)
    
    # Extension check
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    # MIME type check
    mime_type = magic.from_file(str(path), mime=True)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported MIME type: {mime_type}")
    
    # Size check (maximum 50MB)
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("File too large (maximum 50MB)")
    
    return True
```

## 🚨 Backup

### Automatic Backup

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_FILE="compliance.db"

# Create database backup
cp $DB_FILE $BACKUP_DIR/compliance_$DATE.db

# Compress
gzip $BACKUP_DIR/compliance_$DATE.db

# Remove old backups (older than 30 days)
find $BACKUP_DIR -name "compliance_*.db.gz" -mtime +30 -delete

echo "Backup completed: compliance_$DATE.db.gz"
```

### Restore

```bash
#!/bin/bash
# restore.sh

BACKUP_FILE=$1
DB_FILE="compliance.db"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file>"
    exit 1
fi

# Stop application
systemctl stop annex4parser

# Restore database
gunzip -c $BACKUP_FILE > $DB_FILE

# Start application
systemctl start annex4parser

echo "Restore completed from $BACKUP_FILE"
```

## 📈 Scaling

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
version: '3.8'

services:
  annex4parser:
    build: .
    deploy:
      replicas: 3
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres/compliance_db
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: compliance_db
      POSTGRES_USER: annex4user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### Performance Optimization

```python
# Multi-threaded document processing
from concurrent.futures import ThreadPoolExecutor
import threading

def process_documents_parallel(document_paths, session_factory, max_workers=4):
    """Parallel document processing"""
    
    def process_single_document(doc_path):
        session = session_factory()
        try:
            result = ingest_document(Path(doc_path), session)
            return result
        finally:
            session.close()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_single_document, path) 
            for path in document_paths
        ]
        
        results = [future.result() for future in futures]
        return results
```

## 🔄 CI/CD

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy Annex4Parser

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to server
        run: |
          # Deployment commands
          echo "Deploying to production..."
```

---

**System ready for production!** 🚀
