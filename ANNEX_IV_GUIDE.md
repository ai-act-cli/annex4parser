# 🎯 Руководство по работе с Annex IV

## Что изменилось

✅ **Парсер теперь понимает ANNEX IV** и режет их на вложенные пункты:
- `AnnexIV` (корневой)
- `AnnexIV.1`, `AnnexIV.2`, ... (подразделы)  
- `AnnexIV.1.a`, `AnnexIV.1.b`, ... (подпункты)

✅ **Исправлены enum'ы алертов**:
- Добавлен `press_release` и `rss_update` в `alert_type`
- Исправлен маппинг `critical`/`major` → `urgent` приоритет

✅ **Гибкий keyword-маппинг через YAML**:
- Файл `annex4parser/config/keywords.yaml`
- Переменная окружения `ANNEX4_KEYWORDS` для кастомного пути

✅ **Сохранение извлечённого текста**:
- Новое поле `extracted_text` в модели `Document`

✅ **CLI для V2**:
- `python -m annex4parser update-all` для массового обновления
- `python -m annex4parser update-single` для одиночного обновления

## Быстрый старт

### 1. Пересоздать БД (для новых полей)

```bash
# Удаляем старую БД (для dev окружения)
rm -f compliance.db

# Создаем новую схему
python -c "
from annex4parser.models import Base
from sqlalchemy import create_engine
engine = create_engine('sqlite:///compliance.db')
Base.metadata.create_all(engine)
print('✅ БД создана')
"
```

### 2. Обновить все источники (V2)

```bash
python -m annex4parser update-all --db-url sqlite:///compliance.db
```

### 3. Посмотреть извлечённые правила Annex IV

```bash
python examples/extract_annex_iv.py
```

Или через SQL:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser.models import Rule

engine = create_engine("sqlite:///compliance.db")
S = sessionmaker(bind=engine)()

# Все правила Annex IV
for r in S.query(Rule).filter(Rule.section_code.like("AnnexIV%")).order_by(Rule.section_code).all():
    print(f"{r.section_code}: {(r.title or '')[:60]}")
```

### 4. Настроить кастомные ключевые слова

Отредактируйте `annex4parser/config/keywords.yaml`:

```yaml
# Ваши кастомные термины
technical documentation: AnnexIV
conformity assessment: AnnexIV.1
ce marking: AnnexIV.1.a
risk assessment plan: Article9.2
```

Или используйте свой файл:

```bash
export ANNEX4_KEYWORDS=./my_keywords.yaml
```

### 5. Инжест документов с сохранением текста

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from annex4parser import ingest_document

engine = create_engine("sqlite:///compliance.db")
S = sessionmaker(bind=engine)()

# Теперь extracted_text сохраняется автоматически
doc = ingest_document(
    Path("AI_Risk_Assessment.pdf"), 
    S, 
    ai_system_name="MyAI", 
    document_type="risk_assessment"
)

print(f"Документ сохранён с ID: {doc.id}")
print(f"Текст извлечён: {len(doc.extracted_text)} символов")
```

## Структура Annex IV

После парсинга вы получите иерархию:

```
AnnexIV - Technical documentation referred to in Article 11(1)
├─ AnnexIV.1 - General information
│  ├─ AnnexIV.1.a - Name and contact details
│  └─ AnnexIV.1.b - Description of AI system
├─ AnnexIV.2 - Detailed description
│  ├─ AnnexIV.2.a - System architecture
│  └─ AnnexIV.2.b - Dataset description
└─ AnnexIV.3 - Monitoring and logging
   └─ AnnexIV.3.a - Post-market monitoring plan
```

## Миграция БД

Для production используйте Alembic:

```bash
# Создать миграцию
alembic revision --autogenerate -m "Add extracted_text and alert enums"

# Применить
alembic upgrade head
```

Для SQLite в dev можно просто пересоздать БД (см. выше).

## Troubleshooting

**Проблема**: Не находит Annex IV
- **Решение**: Проверьте, что источники в `sources.yaml` содержат полный текст AI Act с Annex'ами

**Проблема**: Ошибка enum при создании алерта
- **Решение**: Убедитесь, что БД обновлена с новыми enum значениями

**Проблема**: Keyword маппинг не работает
- **Решение**: Проверьте путь к `keywords.yaml` и формат файла

## Источники

- [EUR-Lex AI Act](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AL_202401689)
- [Annex IV структура](https://artificialintelligenceact.eu/annex/4/)
