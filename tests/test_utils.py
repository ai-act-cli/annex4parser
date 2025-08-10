from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
import re


def test_extract_celex_id_handles_letters():
    m = re.search(r'CELEX%3A([A-Z0-9]+)', '...CELEX%3A52021PC0206', re.IGNORECASE)
    assert m.group(1) == '52021PC0206'
