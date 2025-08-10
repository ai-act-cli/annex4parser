import yaml
import pathlib

def test_no_placeholder_urls():
    cfg = yaml.safe_load((pathlib.Path("annex4parser")/"sources.yaml").read_text())
    for s in cfg.get("sources", []):
        url = s.get("url", "")
        assert "YOUR_SAVED_SEARCH_RSS_URL" not in url, f"Placeholder left in {s['id']}"
