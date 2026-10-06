"""The Odoo side: order header + order lines (permissions, units, batching, nothing but reads)."""
import pytest

from app.config import get_settings
from app.resolver.resolver import SONotFound, SOResolver
from tests.fake_odoo import FakeOdoo, build_dataset


def resolve(odoo, so="S00123", login="alice"):
    return SOResolver(odoo.client(login), get_settings()).resolve(so)


def group(res, gid):
    return next(g for g in res["groups"] if g["id"] == gid)


@pytest.fixture
def o():
    return build_dataset(FakeOdoo())


def test_only_header_references_and_lines_are_resolved_and_only_those_models_are_read(o):
    res = resolve(o)
    assert [g["id"] for g in res["groups"]] == ["header", "references", "lines"]
    assert [g["label"] for g in res["groups"]] == ["Sales Order", "Reference", "Order lines"]
    assert all(g["status"] == "ok" for g in res["groups"])
    assert {m for m, _ in o.calls if m != "fields_get"} <= {
        "sale.order", "sale.order.line", "product.product", "stock.picking", "stock.move"}


def test_references_list_the_orders_transfers_with_the_lines_each_one_moves(o):
    refs = group(resolve(o), "references")["rows"]
    assert [r["label"] for r in refs] == ["PL1/OUT/00031"]  # only the transfer whose Sales Order is this SO
    done = refs[0]
    assert done["fields"]["ref.contact"]["display"] == "ACME Ltd" and done["fields"]["ref.state"]["display"] == "Done"
    assert done["fields"]["ref.origin"]["display"] == "S00123" and done["line_ids"] == [11]


def test_only_transfers_leaving_from_the_configured_source_location_are_offered(o, monkeypatch):
    from app.config import get_settings
    assert [r["label"] for r in group(resolve(o), "references")["rows"]] == ["PL1/OUT/00031"]  # not PL2/OUT/00033
    monkeypatch.setenv("REFERENCE_SOURCE_LOCATION", "")
    get_settings.cache_clear()
    try:
        assert [r["label"] for r in group(resolve(o), "references")["rows"]] == ["PL2/OUT/00033", "PL1/OUT/00031"]
    finally:
        get_settings.cache_clear()


def test_an_order_without_transfers_has_an_empty_reference_group(o):
    assert group(resolve(o, "S00124"), "references")["status"] == "empty"


def test_denied_transfers_do_not_break_header_or_lines(o):
    o.deny = {"stock.picking"}
    res = resolve(o)
    assert group(res, "references")["status"] == "not_accessible"
    assert group(res, "lines")["status"] == "ok" and group(res, "header")["status"] == "ok"


def test_header_values_and_labels(o):
    header = group(resolve(o), "header")["rows"][0]["fields"]
    assert header["header.name"]["display"] == "S00123" and header["header.name"]["label"] == "SO number"
    assert header["header.customer"]["display"] == "ACME Ltd"
    assert header["header.customer_ref"]["display"] == "PO-77"
    assert header["header.state"]["display"] == "Sales Order" and header["header.state"]["raw"] == "sale"


def test_lines_carry_code_name_and_quantity_with_unit(o):
    lines = group(resolve(o), "lines")["rows"]
    assert [r["row_id"] for r in lines] == ["lines:11"]  # note line and the code-less "Surcharge" line are not listed
    f = lines[0]["fields"]
    assert set(f) == {"line.product.code", "line.product.name", "line.qty"}
    assert f["line.product.code"]["display"] == "220-TD"
    assert f["line.product.name"]["display"] == "Thermometer Cut Corner Square 140x140mm, Cedar"
    assert f["line.qty"]["display"] == "10" and f["line.qty"]["uom"] == "Units"
    assert lines[0]["line_id"] == 11 and lines[0]["disabled"] is False


def test_lines_without_an_item_code_are_not_listed(o):
    rows = group(resolve(o), "lines")["rows"]
    assert all(r["fields"]["line.product.code"]["display"] for r in rows)


def test_zero_quantity_lines_are_flagged_disabled(o):
    rows = {r["row_id"]: r for r in group(resolve(o, "S00125"), "lines")["rows"]}
    assert rows["lines:15"]["disabled"] is True and rows["lines:15"]["disabled_kind"] == "no_qty"
    assert "0" in rows["lines:15"]["disabled_reason"]
    assert rows["lines:16"]["disabled"] is False and rows["lines:16"]["disabled_kind"] == ""


def test_denied_order_lines_are_not_accessible_but_header_still_loads(o):
    o.deny = {"sale.order.line"}
    res = resolve(o)
    assert group(res, "lines")["status"] == "not_accessible" and group(res, "header")["status"] == "ok"


def test_user_without_access_to_the_so_gets_not_found(o):
    o.hide_so_from = {8}
    with pytest.raises(SONotFound):
        resolve(o, login="bob")
    assert resolve(o, login="alice")["so"] == "S00123"


def test_unknown_so(o):
    with pytest.raises(SONotFound):
        resolve(o, "NOPE")


def test_resolution_is_batched_not_per_record(o):
    resolve(o, "S00125")
    for model in ("sale.order.line", "product.product"):
        assert sum(1 for m, meth in o.calls if m == model and meth in ("search_read", "read")) == 1, model


def test_only_read_methods_reach_odoo(o):
    resolve(o)
    assert {meth for _, meth in o.calls} <= {"search_read", "read", "search", "fields_get", "read_group"}


def test_unit_field_rename_is_detected_from_fields_get():
    o18 = build_dataset(FakeOdoo(version="18"))  # sale.order.line.product_uom -> product_uom_id
    assert group(resolve(o18), "lines")["rows"][0]["fields"]["line.qty"]["uom"] == "Units"
