import asyncio
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Base, Source
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock


def test_html_fallback_when_sparql_fails(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    src = Source(
        id="ai_act_html",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024R1689",
        type="eli_sparql",
        freq="6h",
        active=True,
        extra={"celex_id": "32024R1689"},
    )
    db.add(src)
    db.commit()
    mon = RegulationMonitorV2(db)

    async def fake_exec(*args, **kwargs):
        return None

    async def fake_html(*args, **kwargs):
        return "Artificial Intelligence Act\nArticle 1...\n"

    monkeypatch.setattr(mon, "_execute_sparql_query", fake_exec)
    monkeypatch.setattr(mon, "_fetch_html_text", fake_html)

    out = asyncio.run(mon._process_eli_source(src, AsyncMock()))
    assert out and out["type"] == "eli_sparql"
