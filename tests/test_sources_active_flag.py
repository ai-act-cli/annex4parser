from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Base, Source
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import yaml

def test_active_flag_respected(tmp_path: Path):
    cfg = {
        "sources": [
            {"id": "x", "type": "rss", "url": "https://example.com/rss.xml", "freq": "6h", "active": False}
        ]
    }
    cfgp = tmp_path / "sources.yaml"
    cfgp.write_text(yaml.safe_dump(cfg))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    RegulationMonitorV2(db, config_path=cfgp)
    s = db.query(Source).filter_by(id="x").first()
    assert s and s.active is False
