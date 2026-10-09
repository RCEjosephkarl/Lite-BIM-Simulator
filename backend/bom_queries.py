"""Shared cutting/BOM SQL for unchanged persisted views and scoped navigation.

Only trusted relation/column fragments are interpolated. User identifiers are
bound by db.bom_rows. Navigation IDs are JSON-only, never extra CSV columns.
"""

CUTTING_SELECT = """SELECT
{member_ids}    t.category, t.name AS element, t.nzs_ref,
    e.storey, e.segment_id AS segment, e.segment_label, e.type_code,
    e.size AS section_size, e.grade, e.treatment, e.material, e.plies,
    CASE WHEN instr(e.size, '/') > 0
         THEN CAST(substr(e.size, 1, instr(e.size, '/') - 1) AS INTEGER)
         ELSE 1 END AS section_plies,
    SUM(e.length_mm) AS length_mm,
    e.unit_price_usd_per_lm, e.price_confidence,
    e.price_source_name, e.price_source_url, e.price_source_date,
    e.price_currency, e.price_source_currency, e.price_fx_rate,
    e.price_fx_date, e.price_fx_source, e.pricing_notes,
    CASE WHEN e.physical_member_id <> '' THEN 'known'
         WHEN e.type_code LIKE 'truss_%' THEN 'legacy_unknown'
         ELSE 'single_member' END AS cut_identity_status
FROM {relation} e
JOIN element_types t ON t.code=e.type_code
WHERE t.category <> 'concrete'
GROUP BY e.source, e.source_id, e.storey,
         CASE WHEN e.physical_member_id <> '' THEN 'cut:' || e.physical_member_id
              ELSE 'row:' || e.id END"""

BOM_SELECT = """WITH pieces AS (
    SELECT *,
        CASE WHEN plies * section_plies > 1
             THEN (plies * section_plies) || '/' ||
                  CASE WHEN instr(section_size, '/') > 0
                       THEN substr(section_size, instr(section_size, '/') + 1)
                       ELSE section_size END
             ELSE section_size END AS size,
        (CAST(length_mm / 300 AS INTEGER)
         + CASE WHEN length_mm > CAST(length_mm / 300 AS INTEGER) * 300
                THEN 1 ELSE 0 END) * 300 AS stock_mm
    FROM cutting_pieces
)
SELECT
{member_ids}    category, element, storey, segment, size, section_size,
    grade, treatment, material, plies, section_plies,
    stock_mm / 1000.0 AS stock_length_m,
    COUNT(*) AS qty,
    SUM(plies * section_plies) AS physical_qty,
    ROUND(SUM(length_mm) / 1000.0, 3) AS total_length_m,
    ROUND(SUM(length_mm * plies) / 1000.0, 3) AS total_effective_length_m,
    ROUND(SUM(length_mm * plies * section_plies) / 1000.0, 3) AS cut_board_m,
    ROUND(SUM(stock_mm * plies * section_plies) / 1000.0, 3) AS stock_board_m,
    unit_price_usd_per_lm,
    ROUND(SUM(length_mm * plies * unit_price_usd_per_lm) / 1000.0, 2) AS total_cost_usd,
    ROUND(SUM(stock_mm * plies * unit_price_usd_per_lm) / 1000.0, 2) AS stock_cost_usd,
    CASE WHEN unit_price_usd_per_lm IS NULL THEN 0 ELSE 1 END AS estimate_complete,
    price_confidence, price_source_name, price_source_url, price_source_date,
    price_currency, price_source_currency, price_fx_rate, price_fx_date,
    price_fx_source, pricing_notes, cut_identity_status, nzs_ref,
    CASE WHEN stock_mm > 6000 THEN 'over 6.0 m — splice or special order' ELSE '' END
    || CASE WHEN cut_identity_status='legacy_unknown'
            THEN '; legacy truss cut identity unknown — review/recreate from its source definition'
            ELSE '' END AS notes
FROM pieces
GROUP BY category, element, storey, segment, size, section_size, grade, treatment,
         material, plies, section_plies, unit_price_usd_per_lm, price_confidence,
         price_source_name, price_source_url, price_source_date, price_currency,
         price_source_currency, price_fx_rate, price_fx_date, price_fx_source,
         pricing_notes, cut_identity_status, stock_mm, nzs_ref
ORDER BY CASE category
             WHEN 'wall' THEN 1 WHEN 'floor' THEN 2 WHEN 'ceiling' THEN 3
             WHEN 'roof' THEN 4 WHEN 'outdoor' THEN 5 ELSE 6 END,
         element, stock_mm"""

def cutting_select(relation="elements", include_members=False):
    return CUTTING_SELECT.format(relation=relation,
        member_ids="    GROUP_CONCAT(e.id) AS member_ids_csv,\n" if include_members else "")


def bom_select(include_members=False):
    return BOM_SELECT.format(member_ids=
        "    GROUP_CONCAT(member_ids_csv) AS member_ids_csv,\n" if include_members else "")


def navigation_query(where="1"):
    return ("WITH scoped_elements AS (SELECT * FROM elements WHERE " + where + "),\n"
            "cutting_pieces AS (" + cutting_select("scoped_elements", True) + "),\n"
            + bom_select(True).removeprefix("WITH "))
