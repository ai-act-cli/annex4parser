import pytest
from annex4parser.regulation_monitor_v2 import RegulationMonitorV2
from annex4parser.models import Regulation, Rule
from annex4parser.regulation_monitor import canonicalize


def test_relink_children_on_section_code_change(test_db, test_config_path):
    monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
    reg = Regulation(name="Reg", celex_id="CID", version="1")
    test_db.add(reg)
    test_db.flush()

    parent = Rule(
        regulation_id=reg.id,
        section_code="Article6",
        title="",
        content="",
        version="1",
    )
    test_db.add(parent)
    test_db.flush()

    child = Rule(
        regulation_id=reg.id,
        parent_rule_id=parent.id,
        section_code="Article6.1",
        title="",
        content="",
        version="1",
    )
    test_db.add(child)
    test_db.commit()

    code_map = {canonicalize(r.section_code): r for r in test_db.query(Rule).all()}
    old_code = parent.section_code
    new_code = "Article7"
    parent.section_code = new_code
    monitor._relink_children(parent, old_code, new_code, code_map)

    updated_child = test_db.get(Rule, child.id)
    assert updated_child.section_code == "Article7.1"
    assert canonicalize(updated_child.section_code).startswith(new_code)


def test_relink_children_skips_unrelated_codes(test_db, test_config_path):
    monitor = RegulationMonitorV2(test_db, config_path=test_config_path)
    reg = Regulation(name="Reg", celex_id="CID", version="1")
    test_db.add(reg)
    test_db.flush()

    parent = Rule(
        regulation_id=reg.id,
        section_code="Article6",
        title="",
        content="",
        version="1",
    )
    test_db.add(parent)
    test_db.flush()

    child = Rule(
        regulation_id=reg.id,
        parent_rule_id=parent.id,
        section_code="Article60.1",
        title="",
        content="",
        version="1",
    )
    test_db.add(child)
    test_db.commit()

    code_map = {canonicalize(r.section_code): r for r in test_db.query(Rule).all()}
    old_code = parent.section_code
    new_code = "Article7"
    parent.section_code = new_code
    monitor._relink_children(parent, old_code, new_code, code_map)

    updated_child = test_db.get(Rule, child.id)
    assert updated_child.section_code == "Article60.1"
