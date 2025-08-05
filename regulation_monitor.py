# regulation_monitor.py
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import Regulation, Rule
from datetime import datetime

def fetch_regulation_text(url: str) -> str:
    """Получить текст нормативного документа (HTML→текст)."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    return soup.get_text(separator="\n")

def parse_rules(raw_text: str) -> list[dict]:
    """
    Разбить текст закона на статьи/пункты и вернуть список словарей с
    ключами: section_code, title, content.
    Это место для доработки: пока разделяем по строкам 'Article'.
    """
    rules = []
    for block in raw_text.split("\nArticle"):
        block = block.strip()
        if not block:
            continue
        # простейший парсер: отделяем код до первой точки
        first_line, *rest = block.split("\n", 1)
        section_code = first_line.split()[0]
        title = " ".join(first_line.split()[1:]) if len(first_line.split()) > 1 else section_code
        content = rest[0] if rest else ""
        rules.append({
            "section_code": f"Article{section_code}",
            "title": title,
            "content": content,
        })
    return rules

def update_regulation(db: Session, name: str, version: str, url: str) -> None:
    """
    Скачивает текущий текст регламента, сравнивает с сохранённым и обновляет
    таблицы Regulation и Rule при изменениях.
    """
    raw_text = fetch_regulation_text(url)
    existing_reg = db.query(Regulation).filter_by(name=name, version=version).first()
    if existing_reg:
        # в этом MVP просто возвращаем, если такая версия уже есть
        return
    reg = Regulation(
        name=name,
        version=version,
        source_url=url,
        effective_date=datetime.utcnow(),
        last_updated=datetime.utcnow(),
        status="active",
    )
    db.add(reg)
    db.flush()  # чтобы получить id для связи
    for rule_data in parse_rules(raw_text):
        rule = Rule(
            regulation_id=reg.id,
            section_code=rule_data["section_code"],
            title=rule_data["title"],
            content=rule_data["content"],
            risk_level="medium",
            version=version,
            effective_date=datetime.utcnow(),
            last_modified=datetime.utcnow(),
        )
        db.add(rule)
    db.commit()
