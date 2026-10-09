import assert from 'node:assert/strict';
import { decodeDraft } from '../src/drafts.ts';
import { csvRows, writeCsv } from '../src/csv.ts';

const rules = { label: { type: 'text' }, level: { type: 'number' }, checked: { type: 'boolean' },
  type: { type: 'choice', choices: ['common', 'custom'] }, nodes_csv: { type: 'text' }, members_csv: { type: 'text' } };
const versioned = { schema_version: 2, kind: 'wall', project_id: 'home', saved_at: '2026-10-09T00:00:00Z',
  fields: { label: '<b>Literal draft</b>', level: '', checked: false, type: 'custom' }, openings: [] };
const decode = (value, kind = 'wall', project = 'home') => decodeDraft(typeof value === 'string' ? value : JSON.stringify(value), kind, project, rules);
assert.deepEqual(decode(versioned).draft, versioned);
assert.equal(decode(versioned).migrated, false);
const opening={opening_id:'O1',opening_type:'window',start_offset_mm:'1000',width_mm:'',height_mm:'1200',sill_height_mm:'900',head_height_mm:'',lintel_size:'',notes:''};
assert.deepEqual(decode({...versioned,openings:[opening]}).draft.openings,[opening]);
const oldOpening={...opening,start_offset_mm:1000,width_mm:1200,height_mm:1200,sill_height_mm:900,head_height_mm:null};
const migrated=decode({...versioned,schema_version:1,openings:[oldOpening]});
assert.ok(migrated.migrated);assert.equal(migrated.draft.schema_version,2);assert.equal(migrated.draft.openings[0].width_mm,'1200');
assert.equal(migrated.draft.openings[0].head_height_mm,'');
assert.throws(()=>decode({...versioned,openings:[{...opening,width_mm:'NaN'}]}));
for (const invalid of ['{bad', 'null', '[]', '{}', JSON.stringify({ ...versioned, schema_version: 99 }),
  JSON.stringify({ ...versioned, fields: { checked: 'false' } }), JSON.stringify({ ...versioned, fields: { level: 'NaN' } }),
  JSON.stringify({ ...versioned, fields: { type: 'bogus' } }), JSON.stringify({ ...versioned, fields: { unknown: 'value' } }),
  JSON.stringify({ ...versioned, openings: [{}] }), JSON.stringify({ ...versioned, saved_at: 'bad' }),
  JSON.stringify({ ...versioned, fields: { label: {} } })]) assert.throws(() => decode(invalid));
assert.throws(() => decode(versioned, 'truss'), /different form or home/);
assert.throws(() => decode(versioned, 'wall', 'other'), /different form or home/);
const editDraft = { ...versioned, assembly_id: 'saved-assembly' };
assert.throws(() => decode(editDraft), /different assembly/);
assert.deepEqual(decodeDraft(JSON.stringify(editDraft), 'wall', 'home', rules, 'saved-assembly').draft, editDraft);
assert.throws(() => decode(' '.repeat(2*1024*1024+1)), /size limit/);
const legacyWall = decode({ label: 'Legacy', level: 2, checked: false, openings: [] });
assert.equal(legacyWall.migrated, true);
assert.equal(legacyWall.draft.fields.level, '2');
assert.equal(legacyWall.draft.fields.checked, false);
const unfinished = decode({ label: 'Unfinished', level: '', type: 'custom', nodes: [], members: [],
  nodes_csv: 'id,x,y\nINVALID,NaN,0', members_csv: 'unfinished,row' }, 'truss');
assert.equal(unfinished.draft.fields.nodes_csv, 'id,x,y\nINVALID,NaN,0');
const oldCustom = decode({ nodes: [{ id: 'A,"quoted"', x: 0, y: 10 }], members: [{ start_node: 'A,"quoted"', end_node: 'B', element_type: 'web', size: '90x45', material: 'SG8' }] }, 'truss');
assert.equal(oldCustom.draft.fields.nodes_csv, '"A,""quoted""","0","10"');
assert.throws(() => decode({ nodes: [{ id: 'A', x: 'NaN', y: 0 }], members: [] }, 'truss'), /custom truss data/);
const quotedRows = [['A,"quoted"', '10', '20'], ['New\nnode', '30', '40']];
assert.deepEqual(csvRows(writeCsv(quotedRows)), quotedRows);
console.log('Draft contracts passed: version/home/form boundaries, typed/finite/choice fields, legacy conversion, quoted custom CSV, unfinished drafts and recovery limits.');
