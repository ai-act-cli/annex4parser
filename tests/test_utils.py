import re


def test_extract_celex_id_handles_letters():
    pattern = re.compile(r'(?:CELEX%3A|CELEX:)([A-Z0-9]+)', re.IGNORECASE)
    assert pattern.search('...CELEX%3A52021PC0206').group(1) == '52021PC0206'
    assert pattern.search('...CELEX:52021PC0206').group(1) == '52021PC0206'
