FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY annex4parser/ ./annex4parser/
COPY examples/ ./examples/
COPY tests/ ./tests/
COPY rules/ ./rules/

RUN useradd -m -u 1000 annex4parser
USER annex4parser

CMD ["sh", "-c", "risk-detector sync_rules --db-url \"$DATABASE_URL\" --dir /app/rules/risk && python -m annex4parser.scheduler"]
