import assert from 'node:assert/strict';
import {validationIssues,wallDraftSummary,trussDraftSummary} from '../src/formGuidance.ts';

const issues=validationIssues([{loc:['body','openings',1,'width_mm'],msg:'Input should be greater than 0'},
  {loc:['body','nodes',3,'x'],msg:'Value error, must be finite'}]);
assert.deepEqual(issues,[{path:['openings',1,'width_mm'],message:'Input should be greater than 0'},
  {path:['nodes',3,'x'],message:'must be finite'}]);
assert.deepEqual(validationIssues('A stale revision'),[]);
assert.deepEqual(validationIssues([{loc:{bad:1},msg:'Bad'},{loc:['body'],msg:null}]),[]);
const values={start_x_mm:'-1000',start_z_mm:'2000',end_x_mm:'2000',end_z_mm:'6000',wall_height_mm:'2800'};
const opening={opening_id:'A',opening_type:'window',start_offset_mm:'1000',width_mm:'900',height_mm:'1200',sill_height_mm:'900',head_height_mm:'2200',lintel_size:'',notes:''};
const conflict=wallDraftSummary(values,[opening]);assert.ok(conflict.text.includes('5000.0 mm'));assert.ok(conflict.text.includes('53.1°'));
assert.equal(conflict.issues[0].path.at(-1),'head_height_mm');assert.ok(conflict.issues[0].message.includes('2100 mm'));
assert.equal(wallDraftSummary(values,[{...opening,head_height_mm:''}]).issues.length,0);
assert.equal(wallDraftSummary({...values,wall_height_mm:'2000'},[{...opening,head_height_mm:''}]).issues.length,1);
assert.ok(wallDraftSummary({...values,start_x_mm:''},[]).text.includes('Enter wall coordinates'));
assert.ok(wallDraftSummary({...values,start_x_mm:'0',start_z_mm:'0',end_x_mm:'0',end_z_mm:'0'},[]).issues.length);
assert.ok(trussDraftSummary({quantity:'3',spacing_mm:'900',span_mm:'6000',pitch_deg:'25',truss_type:'common'}).includes('1800.0 mm'));
assert.ok(trussDraftSummary({quantity:'1',spacing_mm:'900',truss_type:'custom'}).includes('Custom CSV'));
assert.ok(trussDraftSummary({quantity:'',spacing_mm:'900'}).includes('Enter quantity'));
console.log('Form contracts passed: structured field paths, blank versus zero, rotated wall dimensions, opening head conflicts and repeated truss layout intent.');
