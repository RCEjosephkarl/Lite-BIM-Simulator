-- Physical-cut and BOM views use the shared SQL in bom_queries.py.
-- migrations.py creates these views atomically with the tables below.
-- TimberBIM Lite — SQLite schema
-- All length units are millimetres unless suffixed otherwise.

-- Idempotent bootstrap only. Forward migrations and regeneration must retain
-- existing tables/data; backend/migrations.py owns PRAGMA user_version.

-- Catalogue of element functions (timber + non-timber visual elements).
CREATE TABLE IF NOT EXISTS element_types (
    code      TEXT PRIMARY KEY,   -- e.g. 'stud', 'lintel'
    name      TEXT NOT NULL,      -- display name
    category  TEXT NOT NULL,      -- 'wall' | 'floor' | 'ceiling' | 'roof' | 'outdoor' | 'concrete'
    nzs_ref   TEXT NOT NULL,      -- NZS 3604:2011 clause / table reference
    color_hex TEXT NOT NULL       -- "color by function" hue
);

-- One row per placed graph segment. Connected segments may share one physical
-- cutting-member ID, e.g. a continuous chord at several web connections.
-- Placement: centre point (cx east, cy north, cz elevation) of a box of
-- length_mm (along member axis) x w_mm (horizontal width) x h_mm (depth),
-- yaw radians from +x(east) toward +y(north), pitch radians (+ rises).
CREATE TABLE IF NOT EXISTS elements (
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
    spacing_mm         REAL,
    layout_id          TEXT NOT NULL DEFAULT '',
    instance_id        TEXT NOT NULL DEFAULT '',
    truss_type         TEXT NOT NULL DEFAULT '',
    member_role        TEXT NOT NULL DEFAULT '',
    start_node         TEXT NOT NULL DEFAULT '',
    end_node           TEXT NOT NULL DEFAULT '',
    engineering_status TEXT NOT NULL DEFAULT 'unchecked',
    panel_id TEXT NOT NULL DEFAULT '',
    joint_id TEXT NOT NULL DEFAULT '',
    opening_id TEXT NOT NULL DEFAULT '',
    physical_member_id TEXT NOT NULL DEFAULT '',
    exterior INTEGER,
    load_bearing INTEGER,
    cut_length_mm REAL,
    price_source_date TEXT NOT NULL DEFAULT '',
    price_currency TEXT NOT NULL DEFAULT 'USD',
    price_source_currency TEXT NOT NULL DEFAULT '',
    price_fx_rate REAL,
    price_fx_date TEXT NOT NULL DEFAULT '',
    price_fx_source TEXT NOT NULL DEFAULT '',
    pricing_notes TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_elements_type ON elements(type_code);
CREATE INDEX IF NOT EXISTS idx_elements_source ON elements(source);
CREATE INDEX IF NOT EXISTS idx_elements_source_id ON elements(source_id);

CREATE TABLE IF NOT EXISTS model_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    batch_id       TEXT PRIMARY KEY,
    source_type    TEXT NOT NULL,
    file_name      TEXT NOT NULL DEFAULT '',
    uploaded_at    TEXT NOT NULL,
    row_count      INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    warning_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS source_definitions (
    definition_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_revisions (
    revision INTEGER PRIMARY KEY,
    saved_at TEXT NOT NULL,
    action TEXT NOT NULL,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    operation_key TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    revision INTEGER NOT NULL
);
