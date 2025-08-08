#!/usr/bin/env python3
"""Пример извлечения и просмотра структуры Annex IV из AI Act.

Этот скрипт демонстрирует, как:
1. Обновить регуляцию через V2 монитор
2. Извлечь все правила Annex IV с иерархией
3. Показать структуру parent/child отношений
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Добавляем путь к annex4parser
sys.path.insert(0, str(Path(__file__).parent.parent))

from annex4parser.models import Base, Rule, Regulation
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2


async def main():
    """Главная функция для демонстрации извлечения Annex IV."""
    
    # Создаем БД
    engine = create_engine("sqlite:///compliance_demo.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    
    with SessionLocal() as session:
        print("🚀 Запускаем обновление всех источников...")
        
        # Инициализируем V2 монитор
        monitor = RegulationMonitorV2(db=session)
        
        # Обновляем все источники
        stats = await monitor.update_all()
        print(f"✅ Обновление завершено: {stats}")
        
        print("\n📋 Извлекаем структуру Annex IV...")
        
        # Находим все правила Annex IV
        annex_iv_rules = (
            session.query(Rule)
            .filter(Rule.section_code.like("AnnexIV%"))
            .order_by(Rule.section_code)
            .all()
        )
        
        if not annex_iv_rules:
            print("⚠️  Annex IV правила не найдены. Возможно, источники не содержат Annex IV или парсер не смог их извлечь.")
            return
        
        print(f"📊 Найдено {len(annex_iv_rules)} правил Annex IV:")
        print()
        
        # Группируем по уровням иерархии
        root_rules = [r for r in annex_iv_rules if r.parent_rule_id is None]
        child_rules = [r for r in annex_iv_rules if r.parent_rule_id is not None]
        
        # Создаем карту parent_id -> children
        children_map = {}
        for rule in child_rules:
            if rule.parent_rule_id not in children_map:
                children_map[rule.parent_rule_id] = []
            children_map[rule.parent_rule_id].append(rule)
        
        def print_rule_tree(rule, indent=0):
            """Рекурсивно печатает дерево правил."""
            prefix = "  " * indent + ("├─ " if indent > 0 else "")
            title_part = f" - {rule.title}" if rule.title else ""
            content_preview = (rule.content or "")[:80].replace("\n", " ")
            if len(rule.content or "") > 80:
                content_preview += "..."
            
            print(f"{prefix}{rule.section_code}{title_part}")
            if content_preview.strip():
                print(f"{'  ' * (indent + 1)}💬 {content_preview}")
            
            # Печатаем дочерние элементы
            if rule.id in children_map:
                for child in sorted(children_map[rule.id], key=lambda x: x.section_code):
                    print_rule_tree(child, indent + 1)
        
        # Печатаем дерево
        for root in sorted(root_rules, key=lambda x: x.section_code):
            print_rule_tree(root)
            print()
        
        print("📈 Статистика:")
        print(f"  • Корневых элементов: {len(root_rules)}")
        print(f"  • Дочерних элементов: {len(child_rules)}")
        print(f"  • Всего правил Annex IV: {len(annex_iv_rules)}")
        
        # Показываем примеры маппинга
        print("\n🔗 Примеры для keyword маппинга:")
        for rule in annex_iv_rules[:5]:  # первые 5 правил
            keywords = []
            content = (rule.content or "").lower()
            
            if "technical documentation" in content:
                keywords.append("technical documentation")
            if "conformity assessment" in content:
                keywords.append("conformity assessment")
            if "risk management" in content:
                keywords.append("risk management")
            if "post-market monitoring" in content:
                keywords.append("post-market monitoring")
            
            if keywords:
                print(f"  • {rule.section_code}: {', '.join(keywords)}")


if __name__ == "__main__":
    print("🔧 Annex IV Extractor - демонстрация парсинга иерархии AI Act")
    print("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
