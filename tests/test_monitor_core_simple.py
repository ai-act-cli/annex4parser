import pytest
import asyncio
import hashlib
from unittest.mock import patch
from types import SimpleNamespace
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Regulation, Rule, ComplianceAlert, RegulationSourceLog, Document


@pytest.mark.asyncio
async def test_new_version_creates_records(test_db, eli_rdf_v1):
    """Тест создания записей при новой версии"""
    mon = RegulationMonitorV2(test_db)
    
    with patch("annex4parser.eli_client.fetch_latest_eli", return_value=eli_rdf_v1), \
         patch("annex4parser.regulation_monitor_v2.sha256",
               side_effect=lambda b: hashlib.sha256(b.encode()).hexdigest()):
        
        await mon._process_eli_source(
            SimpleNamespace(id="celex", url="http://example", type="eli_sparql"),
            None  # не нужен, патч выше
        )

    # --- assertions ---------------------------------------------------
    assert test_db.query(Regulation).count() == 1
    reg = test_db.query(Regulation).first()
    assert test_db.query(Rule).filter_by(regulation_id=reg.id).count() > 0
    assert test_db.query(RegulationSourceLog).filter_by(source_id="celex").count() == 1


@pytest.mark.asyncio
async def test_same_content_no_duplicate(test_db, eli_rdf_v1):
    """Тест пропуска дубликатов при одинаковом контенте"""
    mon = RegulationMonitorV2(test_db)
    
    with patch("annex4parser.eli_client.fetch_latest_eli", return_value=eli_rdf_v1):
        await mon._process_eli_source(SimpleNamespace(id="celex", url="u", type="eli_sparql"), None)
        await mon._process_eli_source(SimpleNamespace(id="celex", url="u", type="eli_sparql"), None)

    assert test_db.query(Regulation).count() == 1        # no second version
    assert test_db.query(RegulationSourceLog).count() == 2  # but fetch logged twice
