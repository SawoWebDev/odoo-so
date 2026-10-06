"""PCS / KGS / CBM modes, UoM safety and overrides (guideline section 9; acceptance tests 4 and 8 - calc part)."""
import pytest

from app.calc.pcs_kgs_cbm import apply_overrides, calculate, convert_qty, fmt_value, parse_override

UNITS = {"id": 1, "name": "Units", "factor": 1.0, "category": 1}
DOZEN = {"id": 2, "name": "Dozens", "factor": 1 / 12, "category": 1}
KG = {"id": 3, "name": "kg", "factor": 1.0, "category": 2}


def meta(**kw):
    base = {"qty": 10.0, "uom": UNITS, "product_uom": UNITS, "unit_weight_kg": 0.35, "unit_volume_m3": 0.0012,
            "packagings": [{"id": 5, "name": "Carton of 4", "qty": 4.0, "barcode": ""}], "line_packaging_id": None}
    base.update(kw)
    return base


def test_mode1_order_line_totals():
    c = calculate(1, meta())
    assert (c.pcs, c.kgs, c.cbm) == (10.0, 3.5, 0.012) and not c.warnings


def test_mode1_converts_units_within_a_category():
    c = calculate(1, meta(qty=2.0, uom=DOZEN))  # 2 dozen = 24 units
    assert c.pcs == 2.0 and c.kgs == 8.4  # weight comes from the product unit, not "2 x 0.35"
    assert convert_qty(2.0, DOZEN, UNITS) == (pytest.approx(24.0), None)


def test_mode1_never_mixes_incompatible_units():
    c = calculate(1, meta(qty=2.0, uom=KG))
    assert c.kgs is None and c.cbm is None
    assert any(w["code"] == "uom_mismatch" for w in c.warnings)


def test_missing_weight_and_volume_warn_and_stay_empty_never_zero():
    c = calculate(1, meta(unit_weight_kg=None, unit_volume_m3=None))
    assert c.kgs is None and c.cbm is None
    assert {w["code"] for w in c.warnings} == {"missing_weight", "missing_volume"}
    assert fmt_value("kgs", c.kgs) == ""  # blank on the label, not "0"


def test_mode2_per_carton_uses_packaging_qty():
    c = calculate(2, meta())
    assert (c.pcs, c.kgs, c.cbm) == (4.0, 1.4, 0.0048)


def test_mode2_prefers_the_packaging_chosen_on_the_line():
    pk = [{"id": 5, "name": "Carton of 4", "qty": 4.0}, {"id": 6, "name": "Box of 2", "qty": 2.0}]
    assert calculate(2, meta(packagings=pk, line_packaging_id=6)).pcs == 2.0
    assert calculate(2, meta(packagings=pk)).pcs == 4.0  # default: the largest


def test_mode2_without_packaging_warns():
    c = calculate(2, meta(packagings=[]))
    assert c.pcs is None and c.warnings[0]["code"] == "no_packaging"


def test_mode3_uses_actual_package_weight_and_qty():
    rows = [{"qty": 6.0, "uom": "Units", "package_id": 400, "package_weight_kg": 2.5}]
    c = calculate(3, meta(), rows)
    assert (c.pcs, c.kgs) == (6.0, 2.5) and c.cbm == 0.0072


def test_mode3_falls_back_to_unit_weight_and_sums_same_units():
    rows = [{"qty": 6.0, "uom": "Units", "package_id": 401, "package_weight_kg": None},
            {"qty": 4.0, "uom": "Units", "package_id": 401, "package_weight_kg": None}]
    c = calculate(3, meta(), rows)
    assert c.pcs == 10.0 and c.kgs == 3.5


def test_mode3_refuses_to_sum_different_units():
    rows = [{"qty": 6.0, "uom": "Units"}, {"qty": 1.0, "uom": "kg"}]
    c = calculate(3, meta(), rows)
    assert c.pcs is None and c.warnings[0]["code"] == "uom_mixed"


def test_mode3_without_delivery_rows_warns():
    assert calculate(3, meta(), []).warnings[0]["code"] == "no_delivery"


def test_mode4_is_prefilled_from_base_mode():
    assert calculate(4, meta(), override_base=1).pcs == 10.0
    assert calculate(4, meta(), override_base=2).pcs == 4.0


def test_overrides_keep_the_calculated_value_and_clear_that_warning():
    c = calculate(1, meta(unit_weight_kg=None))
    out = apply_overrides(c, {"kgs": "12,5"})
    assert out["calculated"]["kgs"] is None and out["overrides"] == {"kgs": 12.5} and out["final"]["kgs"] == 12.5
    assert not any(w["field"] == "kgs" for w in out["warnings"])


def test_override_does_not_hide_other_warnings():
    c = calculate(1, meta(unit_weight_kg=None, unit_volume_m3=None))
    out = apply_overrides(c, {"kgs": 1})
    assert [w["code"] for w in out["warnings"]] == ["missing_volume"]


def test_bad_overrides_are_rejected():
    with pytest.raises(ValueError):
        parse_override("abc")
    with pytest.raises(ValueError):
        parse_override(-1)
    assert parse_override("") is None and parse_override(None) is None
