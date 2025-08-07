import pytest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Regulation, Rule, ComplianceAlert, RegulationSourceLog, Source
import aiohttp

MOCK_ELI_DATA = {
    "title": "Test Regulation",
    "version": "1.0",
    "text": "Article 1.1 - Scope\nThis Regulation applies to artificial intelligence systems.",
    "date": "2024-01-15"
}

@patch.object(RegulationMonitorV2, '_init_sources', return_value=None)
@pytest.mark.asyncio
async def test_new_version_creates_records(mock_init_sources, test_db, test_config_path):
    mon = RegulationMonitorV2(test_db, config_path=test_config_path)
    src = Source(id="celex", url="https://publications.europa.eu/webapi/rdf/sparql", type="eli_sparql", freq="6h", active=True, extra={"celex_id": "32024R1689"})
    test_db.add(src)
    test_db.commit()
    mock_session = AsyncMock()
    # Удаляем все Regulation и RegulationSourceLog перед тестом для чистоты
    test_db.query(RegulationSourceLog).delete()
    test_db.query(Regulation).delete()
    test_db.commit()
    with patch.object(RegulationMonitorV2, "_execute_sparql_query", new=AsyncMock(return_value=MOCK_ELI_DATA)), \
         patch("annex4parser.regulation_monitor.parse_rules", return_value=[{"section_code": "1.1", "title": "Scope", "content": "This Regulation applies to AI."}]), \
         patch("annex4parser.legal_diff.LegalDiffAnalyzer.analyze_changes", return_value=SimpleNamespace(severity="medium", change_type="addition")), \
         patch("annex4parser.legal_diff.LegalDiffAnalyzer.get_change_summary", return_value="Test summary"):
        await mon._process_eli_source(
            src,
            mock_session
        )
    # Диагностика: выводим все Regulation
    print("Regulations in DB:", test_db.query(Regulation).all())
    assert test_db.query(Regulation).count() == 1
    reg = test_db.query(Regulation).first()
    assert test_db.query(Rule).filter_by(regulation_id=reg.id).count() > 0
    assert test_db.query(RegulationSourceLog).filter_by(source_id="celex").count() == 1

@patch.object(RegulationMonitorV2, '_init_sources', return_value=None)
@pytest.mark.asyncio
async def test_same_content_no_duplicate(mock_init_sources, test_db, test_config_path):
    mon = RegulationMonitorV2(test_db, config_path=test_config_path)
    src = Source(id="celex", url="https://publications.europa.eu/webapi/rdf/sparql", type="eli_sparql", freq="6h", active=True, extra={"celex_id": "32024R1689"})
    test_db.add(src)
    test_db.commit()
    with patch.object(RegulationMonitorV2, "_execute_sparql_query", new=AsyncMock(return_value=MOCK_ELI_DATA)), \
         patch("annex4parser.regulation_monitor.parse_rules", return_value=[{"section_code": "1.1", "title": "Scope", "content": "This Regulation applies to AI."}]), \
         patch("annex4parser.legal_diff.LegalDiffAnalyzer.analyze_changes", return_value=SimpleNamespace(severity="medium", change_type="addition")), \
         patch("annex4parser.legal_diff.LegalDiffAnalyzer.get_change_summary", return_value="Test summary"):
        await mon._process_eli_source(
            src,
            AsyncMock()
        )
        await mon._process_eli_source(
            src,
            AsyncMock()
        )
    assert test_db.query(Regulation).count() == 1
    assert test_db.query(RegulationSourceLog).count() == 2

@pytest.mark.asyncio
async def test_press_api_alert_created(test_db, test_config_path):
    mon = RegulationMonitorV2(test_db, config_path=test_config_path)
    with patch.object(mon, '_init_sources', return_value=None):
        src = Source(id="ec_press_pdf", url="https://ec.europa.eu/commission/presscorner/api/", type="press_api", active=True)
        test_db.add(src)
        test_db.commit()
        fake_event = {"title": "AI Act: Commission welcomes deal"}

        class FakeResponse:
            status = 200
            async def json(self): return {"events": [fake_event]}
            async def __aenter__(self): return self
            async def __aexit__(self, exc_type, exc, tb): pass
            def raise_for_status(self): pass

        async with aiohttp.ClientSession() as session:
            with patch.object(session, "get", return_value=FakeResponse()):
                await mon._process_press_api_source(
                    src,
                    session
                )
    assert test_db.query(ComplianceAlert).count() == 1
