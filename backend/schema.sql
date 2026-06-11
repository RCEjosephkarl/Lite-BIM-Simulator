-- TimberBIM Lite — SQLite schema
-- All length units are millimetres unless suffixed otherwise.

DROP VIEW IF EXISTS bom;
DROP TABLE IF EXISTS elements;
DROP TABLE IF EXISTS element_types;
DROP TABLE IF EXISTS model_meta;
DROP TABLE IF EXISTS import_batches;

-- Catalogue of element functions (timber + non-timber visual elements).
CREATE TABLE element_types (
    code      TEXT PRIMARY KEY,   -- e.g. 'stud', 'lintel'
    name      TEXT NOT NULL,      -- display name
    category  TEXT NOT NULL,      -- 'wall' | 'floor' | 'ceiling' | 'roof' | 'outdoor' | 'concrete'
    nzs_ref   TEXT NOT NULL,      -- NZS 3604:2011 clause / table reference
    color_hex TEXT NOT NULL       -- "color by function" hue
);

-- One row per physical member placed in the 3D model.
-- Placement: centre point (cx east, cy north, cz elevation) of a box of
-- length_mm (along member axis) x w_mm (horizontal width) x h_mm (depth),
-- yaw radians from +x(east) toward +y(north), pitch radians (+ rises).
CREATE TABLE elements (
    id        INTEGER PRIMARY KEY,
    type_code TEXT NOT NULL REFERENCES element_types(code),
    storey    INTEGER NOT NULL,
    size      TEXT NOT NULL,      -- e.g. '90x45', '2/140x45'
    grade     TEXT NOT NULL,      -- e.g. 'SG8', 'concrete'
    treatment TEXT NOT NULL,      -- e.g. 'H1.2', 'H3.2', '-'
    length_mm REAL NOT NULL CHECK (length_mm > 0),
    w_mm      REAL NOT NULL,
    h_mm      REAL NOT NULL,
    cx        REAL NOT NULL,
    cy        REAL NOT NULL,
    cz        REAL NOT NULL,
    yaw       REAL NOT NULL DEFAULT 0,
    pitch     REAL NOT NULL DEFAULT 0,
    note      TEXT NOT NULL DEFAULT '',
    material  TEXT NOT NULL DEFAULT 'SG8',   -- display name, e.g. 'HySPAN'
    plies     INTEGER NOT NULL DEFAULT 1,    -- wall-frame plies (1..6)
    segment_id    TEXT DEFAULT '',           -- e.g. 'G-EXT-001' (walls only)
    segment_label TEXT DEFAULT '',
    stud_spacing_mm INTEGER,                 -- effective wall stud centres
    unit_price_usd_per_lm REAL,              -- estimating data, NULL = unpriced
    price_confidence   TEXT DEFAULT '',      -- 'high' | 'medium' | 'low'
    price_source_name  TEXT DEFAULT '',
    price_source_url   TEXT DEFAULT '',
    source             TEXT NOT NULL DEFAULT 'generated',
    source_id          TEXT NOT NULL DEFAULT '',
    editable           INTEGER NOT NULL DEFAULT 0,
    confidence         REAL,
    warnings           TEXT NOT NULL DEFAULT '[]',
    truss_id           TEXT NOT NULL DEFAULT '',
    truss_label        TEXT NOT NULL DEFAULT '',
    pitch_deg          REAL,
    span_mm            REAL,
    spacing_mm         REAL
);

CREATE INDEX idx_elements_type ON elements(type_code);
CREATE INDEX idx_elements_source ON elements(source);
CREATE INDEX idx_elements_source_id ON elements(source_id);

CREATE TABLE model_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE import_batches (
    batch_id       TEXT PRIMARY KEY,
    source_type    TEXT NOT NULL,
    file_name      TEXT NOT NULL DEFAULT '',
    uploaded_at    TEXT NOT NULL,
    row_count      INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    warning_count  INTEGER NOT NULL DEFAULT 0
);

-- Bill of materials: TIMBER ONLY (concrete excluded), grouped by function,
-- size, grade, treatment, material, plies and stock length. Stock length =
-- piece length rounded up to the next 300 mm increment (integer arithmetic —
-- no CEIL() in stock SQLite). Pieces over 6.0 m keep their rounded length but
-- are flagged for splicing / special order. Multi-ply wall members show a
-- 'N/size' display size (unless the size already carries a lintel-style
-- prefix) and cost = effective length (length x plies) x unit price.
CREATE VIEW bom AS
WITH pieces AS (
    SELECT
        t.category,
        t.name              AS element,
        e.storey,
        e.segment_id        AS segment,
        CASE WHEN e.plies > 1 AND instr(e.size, '/') = 0
             THEN e.plies || '/' || e.size
             ELSE e.size END AS size,
        e.grade,
        e.treatment,
        e.material,
        e.plies,
        e.unit_price_usd_per_lm,
        e.price_confidence,
        e.price_source_name,
        e.price_source_url,
        t.nzs_ref,
        e.length_mm,
        ((CAST(e.length_mm AS INTEGER) + 299) / 300) * 300 AS stock_mm
    FROM elements e
    JOIN element_types t ON t.code = e.type_code
    WHERE t.category <> 'concrete'
)
SELECT
    category,
    element,
    storey,
    segment,
    size,
    grade,
    treatment,
    material,
    plies,
    stock_mm / 1000.0                    AS stock_length_m,
    COUNT(*)                             AS qty,
    ROUND(SUM(length_mm) / 1000.0, 2)    AS total_length_m,
    ROUND(SUM(length_mm * plies) / 1000.0, 2) AS total_effective_length_m,
    unit_price_usd_per_lm,
    ROUND(SUM(length_mm * plies * COALESCE(unit_price_usd_per_lm, 0))
          / 1000.0, 2)                   AS total_cost_usd,
    price_confidence,
    price_source_name,
    price_source_url,
    nzs_ref,
    CASE WHEN stock_mm > 6000
         THEN 'over 6.0 m — splice or special order'
         ELSE '' END                     AS notes
FROM pieces
GROUP BY category, element, storey, segment, size, grade, treatment, material, plies,
         unit_price_usd_per_lm, price_confidence, price_source_name,
         price_source_url, stock_mm, nzs_ref
ORDER BY CASE category
             WHEN 'wall' THEN 1 WHEN 'floor' THEN 2 WHEN 'ceiling' THEN 3
             WHEN 'roof' THEN 4 WHEN 'outdoor' THEN 5 ELSE 6 END,
         element, stock_mm;
