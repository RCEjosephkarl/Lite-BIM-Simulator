import assert from 'node:assert/strict';
import {assemblyGroups,assemblyKey,memberSearch,cameraKey} from '../src/modelHierarchy.ts';
const member=(id,extra={})=>({id,storey:1,source:'generated',source_id:'zone',segment_id:'',truss_id:'T1',layout_id:'roof',
  physical_member_id:'chord',panel_id:'',member_role:'bottom_chord',type_code:'truss_bottom_chord',size:'90x45',...extra});
const members=[member(1),member(2,{start_node:'B'}),member(3,{truss_id:'T2'}),member(4,{source:'manual_truss'}),
  member(5,{storey:2}),member(6,{truss_id:'',segment_id:'W1',panel_id:'P1'}),member(7,{truss_id:'',segment_id:'W1',panel_id:'P2'})];
const groups=assemblyGroups(members);assert.equal(groups.length,5);assert.deepEqual(groups[0].members.map(m=>m.id),[1,2]);
assert.equal(groups[0].branch,'Truss layout roof');assert.equal(groups.at(-1).branch,'Walls');
assert.equal(groups.at(-1).members.length,2,'panels retain their logical wall assembly');
assert.notEqual(assemblyKey(members[0]),assemblyKey(members[3]),'source namespace protects equal truss IDs');
assert.equal(assemblyGroups([member(1,{truss_id:''}),member(2,{truss_id:''})]).length,1,'unattached connected physical cuts stay together');
assert.equal(assemblyGroups([member(1,{truss_id:'',physical_member_id:''}),member(2,{truss_id:'',physical_member_id:''})]).length,2);
assert.ok(memberSearch(members[0]).includes('bottom_chord'));
const key=(name,extra={})=>cameraKey({key:name,shiftKey:false,altKey:false,metaKey:false,ctrlKey:false,...extra});
assert.equal(key('ArrowLeft'),'pan-left');assert.equal(key('ArrowUp',{shiftKey:true}),'orbit-up');
assert.equal(key('+'),'zoom-in');assert.equal(key('='),'zoom-in');assert.equal(key('-'),'zoom-out');assert.equal(key('Home'),'fit');
assert.equal(key('Tab'),null);assert.equal(key('ArrowLeft',{ctrlKey:true}),null);assert.equal(key('x'),null);
console.log('Navigation contracts passed: source/level identities, panels/instances/cuts and keyboard camera actions.');
