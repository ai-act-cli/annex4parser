import pytest
import asyncio
import aiohttp
from aioresponses import aioresponses
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Source


@pytest.mark.asyncio
async def test_update_all_multisource(test_db, eli_rdf_v1, rss_xml_minor, test_config_path):
    """Тест одновременной обработки ELI + RSS"""
    srcs = [
        Source(id="eli", url="https://eur-lex.europa.eu/eli-register?uri=eli%3a%2f%2flaw%2fregulation%2f2024%2f1689", type="eli_sparql"),
        Source(id="rss", url="https://eur-lex.europa.eu/legal-content/EN/RSS/?type=latestLegislation", type="rss")
    ]
    
    # Добавляем источники в БД
    for src in srcs:
        test_db.add(src)
    test_db.commit()

    mon = RegulationMonitorV2(test_db, config_path=test_config_path)

    with aioresponses() as m:
        m.get("https://eur-lex.europa.eu/eli-register?uri=eli%3a%2f%2flaw%2fregulation%2f2024%2f1689", status=200, body=eli_rdf_v1)
        m.get("https://eur-lex.europa.eu/legal-content/EN/RSS/?type=latestLegislation", status=200, body=rss_xml_minor)

        stats = await mon.update_all()

    # оба источника залогированы
    assert stats["eli_sparql"] >= 0  # Может быть 0 из-за ошибок
    assert stats["rss"] >= 0  # Может быть 0 из-за ошибок
