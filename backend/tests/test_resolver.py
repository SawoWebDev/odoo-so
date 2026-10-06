"""Acceptance tests 2, 3, 4 (permissions, resolver MTO/resale, UoM)."""
import pytest

from app.config import get_settings
from app.resolver.resolver import SONotFound, SOResolver, to_public
from tests.fake_odoo import FakeOdoo, build_dataset


def resolve(odoo, so="S00123", login="alice"):
    return SOResolver(odoo.client(login), get_settings()).resolve(so)


def group(res, gid):
    return next(g for g in res["groups"] if g["id"] == gid)


def values(g, key):
    return [r["fields"][key]["display"] for r in g["rows"] if key in r["fields"]]


@pytest.fixture
def o():
    return build_dataset(FakeOdoo())


def test_mto_so_links_mo_bom_delivery_lots_and_invoice(o):
    res = resolve(o)
    assert [g["id"] for g in res["groups"]] == ["header", "lines", "products", "bom", "mrp", "purchasing", "delivery", "invoicing"]
    assert all(g["status"] == "ok" for g in res["groups"]), [(g["id"], g["status"], g["message"]) for g in res["groups"]]

    header = group(res, "header")["rows"][0]["fields"]
    assert header["header.name"]["display"] == "S00123"
    assert header["header.customer"]["display"] == "ACME Ltd"
    assert header["header.state"]["display"] == "Sales Order"  # selection label, raw kept
    assert header["header.state"]["raw"] == "sale"

    lines = group(res, "lines")["rows"]
    assert len(lines) == 1  # the note line is skipped
    f = lines[0]["fields"]
    assert f["line.product.code"]["display"] == "220-TD"
    assert f["line.product.barcode"]["display"] == "5901234123457"
    assert f["line.qty"]["display"] == "10" and f["line.qty"]["uom"] == "Units"

    bom = group(res, "bom")
    names = values(bom, "bom.component.name")
    assert names == ["Cedar Frame", "Glass Tube", "Safe Fluid"]  # level 1 x2, level 2 sub-assembly x1
    assert values(bom, "bom.level") == ["1", "1", "2"]
    assert values(bom, "bom.qty_total")[0] == "20"  # 2 per unit x 10 ordered
    assert group(res, "bom")["rows"][2]["fields"]["bom.qty"]["uom"] == "kg"  # UoM never dropped

    mrp = group(res, "mrp")
    assert "MO/00001" in values(mrp, "mrp.name")
    assert values(mrp, "mrp.wo.name") == ["Assemble"]
    assert values(mrp, "mrp.move.lot") == ["LOT-W1"]

    po = group(res, "purchasing")
    assert values(po, "purchase.name") == ["P00001"] and values(po, "purchase.vendor") == ["Cedar Supplier"]

    delivery = group(res, "delivery")
    assert values(delivery, "delivery.lot") == ["LOT-A1", "LOT-A2"]
    assert values(delivery, "delivery.package") == ["PACK0001", "PACK0002"]
    assert values(delivery, "delivery.qty") == ["6", "4"]
    assert {r["fields"]["delivery.qty"]["uom"] for r in delivery["rows"]} == {"Units"}
    assert all(r["line_id"] == 11 for r in delivery["rows"])

    inv = group(res, "invoicing")
    assert values(inv, "invoice.name") == ["INV/2026/0001"] and values(inv, "invoice.amount_total") == ["125"]


def test_resale_so_has_empty_manufacturing_without_errors(o):
    res = resolve(o, "S00124")
    for gid in ("bom", "mrp", "purchasing", "delivery", "invoicing"):
        g = group(res, gid)
        assert g["status"] == "empty" and g["rows"] == [], gid
    assert group(res, "lines")["status"] == "ok"


def test_uninstalled_manufacturing_is_not_installed_not_an_error(o):
    o.missing = {"mrp.production", "mrp.bom", "mrp.workorder"}
    res = resolve(o)
    assert group(res, "mrp")["status"] == "not_installed"
    assert group(res, "bom")["status"] == "not_installed"
    assert group(res, "delivery")["status"] == "ok"


def test_limited_model_access_only_hides_those_groups(o):
    o.deny = {"mrp.production", "purchase.order.line"}
    res = resolve(o)
    assert group(res, "mrp")["status"] == "not_accessible"
    assert group(res, "purchasing")["status"] == "not_accessible"
    assert group(res, "delivery")["status"] == "ok" and group(res, "lines")["status"] == "ok"
    assert group(res, "invoicing")["status"] == "ok"


def test_user_without_access_to_the_so_gets_not_found(o):
    o.hide_so_from = {8}
    with pytest.raises(SONotFound):
        resolve(o, login="bob")
    assert resolve(o, login="alice")["so"] == "S00123"


def test_unknown_so(o):
    with pytest.raises(SONotFound):
        resolve(o, "NOPE")


def test_resolution_is_batched_not_per_record(o):
    resolve(o)
    for model in ("stock.move.line", "stock.move", "stock.picking", "mrp.workorder", "account.move", "product.packaging"):
        n = sum(1 for m, meth in o.calls if m == model and meth in ("search_read", "read"))
        assert n <= 3, f"{model}: {n} calls"


def test_only_read_methods_reach_odoo(o):
    resolve(o)
    assert {meth for _, meth in o.calls} <= {"search_read", "read", "search", "fields_get", "read_group"}


def test_field_renames_across_versions_are_detected_from_fields_get():
    o16 = build_dataset(FakeOdoo(version="16"))  # stock.move.line uses qty_done instead of quantity
    res = resolve(o16)
    assert values(group(res, "delivery"), "delivery.qty") == ["6", "4"]


def test_images_stay_server_side_in_public_payload(o):
    res = resolve(o)
    img = group(res, "lines")["rows"][0]["fields"]["line.product.image"]
    assert isinstance(img["raw"], str) and len(img["raw"]) > 20
    pub = to_public(res)
    pimg = next(g for g in pub["groups"] if g["id"] == "lines")["rows"][0]["fields"]["line.product.image"]
    assert pimg["raw"] is True and pimg["display"] == "[image]"


def test_no_quantity_field_without_uom(o):
    res = resolve(o)
    for g in res["groups"]:
        for r in g["rows"]:
            for k, f in r["fields"].items():
                if k.endswith((".qty", ".qty_received", ".qty_delivered", ".qty_invoiced", ".qty_total")) and f["display"]:
                    assert f["uom"], f"{k} has no UoM"
