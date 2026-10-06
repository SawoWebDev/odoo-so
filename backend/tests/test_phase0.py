"""The Phase 0 report generator runs against the mock and flags what it cannot verify."""
import socket
import threading
import time

import uvicorn

from app.config import Settings
from app.odoo.connect import Connector
from scripts.mock_odoo import create_mock_app
from scripts.phase0_verify import verify
from tests.fake_odoo import FakeOdoo, build_dataset


def test_report_lists_fields_sample_order_and_open_items():
    odoo = build_dataset(FakeOdoo(version="18"))
    del odoo.fields["res.users"]  # (not in the report) - keep the report working
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(create_mock_app(odoo, (18, 0)), host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True); th.start()
    while not server.started:
        time.sleep(0.05)
    try:
        settings = Settings(odoo_url=f"http://127.0.0.1:{port}", odoo_db="db", odoo_transport="jsonrpc")
        conn = Connector(settings)
        client = conn.connect("alice", "pw-alice")
        report = verify(client, settings, "S00123", "jsonrpc", conn.server_info())
    finally:
        server.should_exit = True; th.join(timeout=5)
    assert "# VERIFY REPORT (Phase 0)" in report and "major 18" in report
    assert "### `sale.order.line`" in report
    assert "`product_uom_id`" in report and "alternate" in report  # Odoo 18 rename detected for the unit field
    assert "### `product.product`" in report and "`default_code`" in report
    assert "Sample order `S00123`" in report
    assert "Items that need a human decision" in report and "Gate:" in report
