"""Physical cutting identities and estimate coverage, independent of rendering."""
import math
from decimal import Decimal, ROUND_HALF_UP, localcontext

import materials


def cutting_pieces(elements):
    groups = {}
    for index, member in enumerate(elements):
        if member.get("material", "").lower() == "concrete":
            continue
        identifier = member.get("physical_member_id")
        key = (member.get("source"), member.get("source_id"), member.get("storey"),
               identifier or f"single:{index}")
        group = groups.setdefault(key, {"first": member, "length_mm": 0, "declared": None})
        first = group["first"]
        for field in ("type_code", "size", "material", "grade", "treatment", "plies", "instance_id"):
            if member.get(field) != first.get(field):
                raise ValueError(f"Physical cutting member has inconsistent {field}")
        declared = member.get("cut_length_mm")
        if declared is not None:
            if not isinstance(declared, (int, float)) or not math.isfinite(declared) or declared <= 0:
                raise ValueError("Physical cut length must be finite and positive")
            if not identifier:
                raise ValueError("A declared physical cut requires its member ID")
            if group["declared"] is not None and not math.isclose(declared, group["declared"], abs_tol=.01):
                raise ValueError("Segments disagree about their physical cut length")
            group["declared"] = declared
        group["length_mm"] += member["length_mm"]
    result = []
    for group in groups.values():
        if group["declared"] is not None and not math.isclose(group["length_mm"], group["declared"], abs_tol=.01):
            raise ValueError("Connected segments do not cover the declared physical cut length")
        item = {**group["first"], "length_mm": group["length_mm"]}
        item["stock_mm"] = math.ceil(item["length_mm"] / 300) * 300
        item["board_multiplier"] = item.get("plies", 1) * materials.section_plies(item["size"])
        item["cut_identity_status"] = ("known" if item.get("physical_member_id") else
                                       "legacy_unknown" if item.get("type_code", "").startswith("truss_") else "single_member")
        result.append(item)
    return result


def preview_summary(elements):
    pieces = cutting_pieces(elements)
    unpriced = [piece for piece in pieces if piece.get("unit_price_usd_per_lm") is None]
    # Round each BOM group once, then sum, matching displayed/exported line
    # totals. Graph segments must never create independent rounding lines.
    groups = {}
    fields = ("type_code", "storey", "segment_id", "size", "grade", "treatment",
              "material", "plies", "unit_price_usd_per_lm", "price_confidence",
              "price_source_name", "price_source_url", "price_source_date", "price_currency",
              "price_source_currency", "price_fx_rate", "price_fx_date", "price_fx_source",
              "pricing_notes", "cut_identity_status", "stock_mm")
    for piece in pieces:
        price = piece.get("unit_price_usd_per_lm")
        if price is None:
            continue
        totals = groups.setdefault(tuple(piece.get(field) for field in fields), [0, 0])
        totals[0] += piece["length_mm"] * piece.get("plies", 1) * price
        totals[1] += piece["stock_mm"] * piece.get("plies", 1) * price
    def subtotal(position):
        values = [totals[position] / 1000 for totals in groups.values()]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Price and physical quantities exceed the finite estimating range")
        with localcontext() as context:
            context.prec = 340  # Covers every finite IEEE double through cents.
            total = sum(float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) for value in values)
        if not math.isfinite(total):
            raise ValueError("Estimate total exceeds the finite estimating range")
        return round(total, 2)
    cut_cost, stock_cost = subtotal(0), subtotal(1)
    return {
        "cut_quantity": len(pieces),
        "physical_board_quantity": sum(piece["board_multiplier"] for piece in pieces),
        "cut_board_metres": round(sum(piece["length_mm"]*piece["board_multiplier"] for piece in pieces)/1000, 3),
        "stock_board_metres": round(sum(piece["stock_mm"]*piece["board_multiplier"] for piece in pieces)/1000, 3),
        "unpriced_cut_quantity": len(unpriced),
        "estimate_complete": not unpriced,
        "estimated_cost_usd": round(cut_cost, 2),
        "estimated_stock_cost_usd": round(stock_cost, 2),
        "basis": "priced cut-length subtotal; stock is one rounded blank per physical board, without nesting/offcut reuse",
    }
