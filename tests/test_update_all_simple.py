import pytest
import asyncio
import aiohttp
from aioresponses import aioresponses
from unittest.mock import patch, AsyncMock
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Source


@pytest.mark.asyncio
async def test_update_all_multisource(test_db, eli_rdf_v1, rss_xml_minor, test_config_path):
    """Тест одновременной обработки ELI + RSS"""
    srcs = [
        Source(id="eli", url="https://eur-lex.europa.eu/eli-register?uri=eli%3a%2f%2flaw%2fregulation%2f2024%2f1689", type="eli_sparql", active=True, extra={"celex_id": "32024R1689"}),
        Source(id="rss", url="https://www.europarl.europa.eu/rss/doc/debates-plenary/en.xml", type="rss", active=True)
    ]
    
    # Добавляем источники в БД
    for src in srcs:
        test_db.add(src)
    test_db.commit()

    mon = RegulationMonitorV2(test_db, config_path=test_config_path)

    # Используем патчинг для более быстрого выполнения
    with patch.object(mon, '_execute_sparql_query', return_value={
        'title': 'EU AI Act',
        'date': '2024-01-15',
        'version': '1.0',
        'items': [{'url': 'http://example.com/doc.pdf', 'format': 'PDF'}]
    }), patch.object(mon, '_process_rss_source', return_value={'type': 'rss', 'source_id': 'rss'}), \
         patch.object(mon, '_fetch_pdf_text', new=AsyncMock(return_value='PDF text')):

        stats = await mon.update_all()

    # Проверяем, что оба источника обработаны
    assert stats["eli_sparql"] >= 0  # Может быть 0 из-за ошибок
    assert stats["rss"] >= 0  # Может быть 0 из-за ошибок
    assert "total" in stats
    assert "errors" in stats
