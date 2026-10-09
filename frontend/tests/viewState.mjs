import assert from 'node:assert/strict';
import { WorkspaceState, defaultView, decodeView, memberKey, validCamera, viewFromQuery, viewToQuery } from '../src/workspaceState.ts';
import { boundsOf, clippedCorners, memberEndpoints, sectionContains, wallMetrics } from '../src/memberGeometry.ts';

const data=new Map();
const port={getItem:key=>data.get(key)??null,setItem:(key,value)=>{data.set(key,value);return true;}};
const member=(id=1,extra={})=>({id,type_code:'stud',source:'generated',source_id:'wall-a',storey:1,
  physical_member_id:'cut-a',start_node:'',end_node:'',segment_id:'wall-a',truss_id:'',
  cx:0,cy:0,cz:0,yaw:0,pitch:0,length_mm:1000,w_mm:100,h_mm:40,...extra});
const model=(home='a',revision=0,elements=[member()])=>({elements,types:[{code:'stud',category:'wall'}],
  meta:{project:{project_id:home,revision},frame_segments:[],warnings:[],review:{checks:[]}}});
const state=new WorkspaceState(port);
state.setModel(model());state.select(state.model.elements[0]);state.isolate(state.model.elements);
const camera={position:[20,10,5],target:[0,0,0],near:.1,far:500,projection:'orthographic',ortho_height:30,zoom:2,up:[0,0,-1]};
state.patch({mode:'material',source:'generated',level:1,layers:{roof:false},camera,standardView:'top',dimensions:true,
  section:{axis:'z',position_mm:250,keep:'lower'}});
const saved=structuredClone(state.view);
state.setModel(model('b'));assert.deepEqual(state.view,defaultView());
state.patch({layers:{wall:false},standardView:'side'});state.setModel(model('a',1,[member(999)]));
assert.deepEqual(state.view,saved);assert.equal(state.selectedMember().id,999);
assert.equal(state.visibleMembers().length,1);
assert.notEqual(memberKey(member(1),0),memberKey(member(1,{source:'manual_wall'}),0));
assert.notEqual(memberKey(member(1,{start_node:'A',end_node:'B'}),0),memberKey(member(1,{start_node:'B',end_node:'C'}),0));
assert.notEqual(memberKey(member(1,{physical_member_id:''}),0),memberKey(member(1,{physical_member_id:''}),1));

const replacement=member(-1,{source:'manual_wall',source_id:'wall-a',physical_member_id:'new-cut'});
const preview={elements:[replacement],types:state.model.types,replace_source_id:'wall-a',replace_source_type:'manual_wall',
  metadata:{warnings:[],frame_segments:[],review:{checks:[]}}};
state.beginPreview(preview);
assert.equal(state.activeModel.elements.length,2,'same source ID in generated namespace survives manual replacement');
assert.equal(state.view.source,'');assert.equal(state.view.level,null);assert.equal(state.view.section,null);
state.patch({source:'manual_wall',camera:{...camera,zoom:4},layers:{roof:false,floor:false}});state.persist();
assert.equal(decodeView(data.get('timberbim.view.v1.a'),'a').camera.zoom,2,'preview camera cannot overwrite committed preferences');
state.cancelPreview();assert.equal(state.view.camera.zoom,2);assert.equal(state.view.source,'generated');
assert.equal(state.view.layers.floor,false,'deliberate visibility preferences survive cancellation');
state.setModel(model('a',2,[]));assert.equal(state.view.selection,null);assert.equal(state.view.isolation,null);assert.equal(state.view.source,'');assert.equal(state.view.level,null);

data.set('timberbim.view.v1.corrupt','{bad');state.setModel(model('corrupt'));state.patch({dimensions:true});state.persist();
assert.equal(state.recoveryRaw,'{bad');assert.equal(data.get('timberbim.view.v1.corrupt'),'{bad');
state.discardRecovery();assert.equal(decodeView(data.get('timberbim.view.v1.corrupt'),'corrupt').dimensions,true);
for(const raw of ['null','[]','{}',JSON.stringify({schema_version:1,project_id:'wrong',view:defaultView()}),
  JSON.stringify({schema_version:99,project_id:'corrupt',view:defaultView()}),
  JSON.stringify({schema_version:1,project_id:'corrupt',view:{...defaultView(),layers:{roof:'false'}}})])assert.throws(()=>decodeView(raw,'corrupt'));
const denied=new WorkspaceState({getItem:()=>null,setItem:()=>false});denied.setModel(model());denied.persist();assert.equal(denied.storageUnavailable,true);
assert.ok(validCamera(camera));assert.ok(validCamera({...camera,projection:'perspective',ortho_height:undefined}));
for(const value of [{...camera,zoom:0},{...camera,ortho_height:0},{...camera,far:.01},{...camera,up:[0,0,0]},
  {...camera,position:[Infinity,1,2]},{...camera,position:[1e308,0,0],target:[-1e308,0,0]},
  {...camera,target:camera.position},{...camera,projection:'fisheye'}])assert.equal(validCamera(value),false);

const query=new URLSearchParams('project_id=a&section=wall');viewToQuery(query,saved);
const hints=viewFromQuery(query);assert.equal(hints.standardView,'top');assert.deepEqual(hints.section,saved.section);assert.equal(hints.level,1);
assert.equal(query.get('project_id'),'a');assert.equal(query.get('section'),'wall');
assert.deepEqual(viewFromQuery(new URLSearchParams('view=bogus&level=NaN&section_axis=z&section_mm=Infinity&section_keep=lower')),{});
viewToQuery(query,defaultView());assert.equal(query.has('section_mm'),false);assert.equal(query.has('dimensions'),false);

const bounds=boundsOf([member()]);assert.deepEqual(bounds,{minimum:[-500,-50,-20],maximum:[500,50,20]});
assert.deepEqual(memberEndpoints(member()),[[-500,0,0],[500,0,0]]);
const upright=boundsOf([member(1,{pitch:Math.PI/2})]);assert.ok(Math.abs(upright.maximum[2]-500)<1e-8);assert.ok(Math.abs(upright.maximum[0]-20)<1e-8);
const rotated=boundsOf([member(1,{yaw:Math.PI/4})]);assert.ok(Math.abs(rotated.maximum[0]-550/Math.sqrt(2))<1e-8);
const plane={axis:'x',position_mm:250,keep:'upper'};
assert.deepEqual(boundsOf([member()],plane),{minimum:[250,-50,-20],maximum:[500,50,20]});
assert.ok(clippedCorners(member(),plane).every(p=>p[0]>=250-1e-8));
assert.equal(boundsOf([member()],{...plane,position_mm:501}),null);
assert.equal(sectionContains([249,0,0],plane),false);assert.equal(sectionContains([250,0,0],plane),true);
assert.equal(sectionContains([0,-11,0],{axis:'y',position_mm:-10,keep:'lower'}),true);
assert.equal(boundsOf([]),null);
assert.equal(wallMetrics(Array.from({length:20000},(_,id)=>member(id))).span_mm,1000,'large groups do not overflow argument stack');
console.log('View contracts passed: home/revision identities, reversible previews, scoped recovery, finite cameras/deep links and oriented/clipped geometry.');
