"""Pricing revisions must reconcile model, preview, BOM and downloads."""
import csv
import io

import pytest

import materials
from test_projects import commit_wall, headers, home, scope
from test_smoke import client, manual_wall_payload


def test_prices_persist_per_home_and_update_every_estimate_surface():
    accepted, _ = commit_wall(home())
    model = accepted["model"]
    other = home("Other home", "sample")
    response = client.post("/api/pricing/overrides", params=scope(model), json={"overrides": {"sg8": 99}}, headers=headers(model, key="price-change"))
    assert response.status_code == 200, response.text
    changed = response.json()
    total = sum(e["length_mm"] * e["plies"] * e["unit_price_usd_per_lm"] for e in changed["elements"]) / 1000
    assert changed["meta"]["cost_summary"]["grand_total_usd"] == pytest.approx(total, abs=.01)
    assert all(e["price_confidence"] == "user" for e in changed["elements"])
    rows = client.get("/api/bom.json", params=scope(model)).json()["rows"]
    assert sum(r["total_cost_usd"] for r in rows) == pytest.approx(total, abs=.1)
    exported = list(csv.DictReader(io.StringIO(client.get("/api/bom.csv", params=scope(model)).text)))
    assert sum(float(r["total_cost_usd"]) for r in exported) == pytest.approx(total, abs=.1)
    preview = client.post("/api/manual/wall-frame/preview", params=scope(model), json=manual_wall_payload()).json()
    assert preview["metadata"]["estimated_cost_usd"] == pytest.approx(total, abs=.01)
    assert client.get("/api/pricing", params=scope(model)).json()["overrides"] == {"sg8": 99}
    assert client.get("/api/pricing", params=scope(other)).json()["overrides"] == {}
    assert client.get("/api/model", params=scope(other)).json() == other


@pytest.mark.parametrize("overrides", [{"sg8": -1}, {"missing": 10}, {"sg8": "NaN"}])
def test_invalid_price_override_does_not_change_revision_or_members(overrides):
    model = home("Prices", "sample")
    result = client.post("/api/pricing/overrides", params=scope(model), json={"overrides": overrides}, headers=headers(model))
    assert result.status_code == 422
    assert client.get("/api/model", params=scope(model)).json() == model


def test_unsupported_size_is_unpriced_and_derived_size_is_low_confidence():
    assert materials.unit_price_usd_per_lm("sg10", "240x90")[0] is None
    assert materials.unit_price_usd_per_lm("sg8", "140x45")[1] == "low"
    accepted, _ = commit_wall(home(), {**manual_wall_payload(), "stud_size": "240x90", "stud_material": "SG10"})
    summary = accepted["model"]["meta"]["cost_summary"]
    assert summary["estimate_complete"] is False
    assert summary["coverage"]["unpriced_members"] > 0
