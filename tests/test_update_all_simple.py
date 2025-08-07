import pytest
import asyncio
import aiohttp
from aioresponses import aioresponses
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Source


@pytest.mark.asyncio
async def test_update_all_multisource(test_db, eli_rdf_v1, rss_xml_minor):
    """Тест одновременной обработки ELI + RSS"""
    srcs = [
        Source(id="eli", url="u1", type="eli_sparql"),
        Source(id="rss", url="u2", type="rss")
    ]

    mon = RegulationMonitorV2(test_db)

    with aioresponses() as m:
        m.get("u1", status=200, body=eli_rdf_v1)
        m.get("u2", status=200, body=rss_xml_minor)

        stats = await mon.update_all()

    # оба источника залогированы
    assert stats["eli_sparql"] == 1
    assert stats["rss"] == 1
    assert stats["total"] == 2
