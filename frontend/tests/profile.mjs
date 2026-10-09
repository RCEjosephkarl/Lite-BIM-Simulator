/** Local reference measurements, with isolated backend data and browser storage. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,readFile,writeFile,rm,mkdir,readdir} from 'node:fs/promises';
import {createServer} from 'node:net';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const option=name=>{const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];};
const repeats=Number(option('--repeats')??3);
assert.ok(Number.isInteger(repeats)&&repeats>=1&&repeats<=20,'repeats must be 1–20');
const output=option('--output');
const runtime=await mkdtemp(join(tmpdir(),'timberbim-profile-'));
const python=process.env.TIMBERBIM_TEST_PYTHON??'python3';
let service,browser,logs='';
async function runPython(args){
  const child=spawn(python,args,{cwd:join(root,'backend'),env:{...process.env,TIMBERBIM_DB_PATH:join(runtime,'unused.db')},stdio:['ignore','pipe','pipe']});
  let output='';child.stdout.on('data',data=>output+=data);child.stderr.on('data',data=>output+=data);
  const [code]=await once(child,'exit');assert.equal(code,0,output);
}
try{
  await runPython(['benchmark.py','--repeats',String(repeats),'--output',join(runtime,'backend.json'),'--archives-dir',join(runtime,'archives')]);
  const backend=JSON.parse(await readFile(join(runtime,'backend.json'),'utf8'));
  const reservation=createServer();reservation.listen(0,'127.0.0.1');await once(reservation,'listening');
  const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  const url=`http://127.0.0.1:${port}`;
  service=spawn(python,['-m','uvicorn','server:app','--host','127.0.0.1','--port',String(port),'--log-level','error'],
    {cwd:join(root,'backend'),env:{...process.env,TIMBERBIM_DB_PATH:join(runtime,'server.db')},stdio:['ignore','pipe','pipe']});
  service.stderr.on('data',data=>logs+=data);
  let ready=false;
  for(let i=0;i<100;i++){
    assert.equal(service.exitCode,null,logs);
    try{ready=(await fetch(`${url}/api/health`)).ok;}catch{}
    if(ready)break;await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.ok(ready,logs);
  browser=await chromium.launch({executablePath:process.env.TIMBERBIM_TEST_BROWSER||undefined,headless:true,args:['--no-sandbox']});
  const report={benchmark_schema_version:2,recorded_at:new Date().toISOString(),application_version:backend.application_version,
    source_fingerprint:backend.source_fingerprint,environment:{node:process.version,chromium:browser.version(),headless:true},
    backend,fixtures:[]};
  const request=async(path,body,model,proof)=>{
    const response=await fetch(`${url}${path}${model?`?project_id=${model.meta.project.project_id}`:''}`,{method:'POST',
      headers:{'Content-Type':'application/json',...(model?{'If-Match':String(model.meta.project.revision)}:{}),
        ...(proof?{'X-Preview-Token':proof.preview_token,'Idempotency-Key':crypto.randomUUID()}:{} )},body:JSON.stringify(body)});
    assert.ok(response.ok,await response.clone().text());return response.json();
  };
  for(const filename of (await readdir(join(runtime,'archives'))).sort()){
    const fixture=filename.replace(/\.json$/,'');
    let model=await request('/api/projects',{name:`Profile ${fixture}`,geometry_mode:'custom'});
    const archive=JSON.parse(await readFile(join(runtime,'archives',filename),'utf8'));
    const proof=await request('/api/project/archive/preview',archive,model);
    model=await request('/api/project/archive/commit',archive,model,proof);
    const reference=backend.fixtures.find(f=>f.id===fixture);assert.equal(model.elements.length,reference.member_count);
    const transfer=[];
    for(let i=0;i<repeats;i++){
      const start=performance.now();const response=await fetch(`${url}/api/model?project_id=${model.meta.project.project_id}`);
      assert.ok(response.ok);const text=await response.text();const received=performance.now();const parsed=JSON.parse(text);const end=performance.now();
      assert.equal(parsed.elements.length,reference.member_count);
      transfer.push({loopback_response_and_body_ms:received-start,json_parse_ms:end-received,body_bytes:Buffer.byteLength(text)});
    }
    const contexts=[];
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const context=await browser.newContext({viewport});contexts.push(context);
      const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
      const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
      await page.goto(`${url}/?project_id=${model.meta.project.project_id}&diagnostics=1`);
      await page.locator('#home-status').filter({hasText:'revision'}).waitFor();
      await page.waitForFunction(()=>window.timberbimDiagnostics?.snapshot().renderer.draw_calls>0);
      const heap=async()=>{
        await cdp.send('HeapProfiler.collectGarbage');
        const {metrics}=await cdp.send('Performance.getMetrics');
        return Object.fromEntries(metrics.filter(m=>['JSHeapUsedSize','JSHeapTotalSize','Nodes','Documents','JSEventListeners'].includes(m.name)).map(m=>[m.name,m.value]));
      };
      const before={metrics:await page.evaluate(()=>window.timberbimDiagnostics.snapshot()),heap:await heap()};
      await page.evaluate(()=>window.timberbimDiagnostics.reset());
      for(let i=0;i<repeats;i++){
        await page.evaluate(()=>window.timberbimDiagnostics.rebuild());
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      }
      const ids=model.elements.filter(e=>e.material!=='concrete').map(e=>e.id);
      const selected=[];
      for(let i=0;i<Math.min(20,ids.length);i++)selected.push(ids[Math.floor(i*ids.length/Math.min(20,ids.length))]);
      let hits=0;
      for(const id of selected){
        await page.evaluate(id=>window.timberbimDiagnostics.select(id),id);
        if(await page.evaluate(id=>window.timberbimDiagnostics.rayPick(id),id))hits++;
      }
      // Wait for controls to settle, then verify no idle renderer submissions.
      await page.waitForFunction(()=>!window.timberbimDiagnostics.snapshot().render_pending);
      const operationTimings=await page.evaluate(()=>window.timberbimDiagnostics.snapshot().timings);
      await page.evaluate(()=>window.timberbimDiagnostics.reset());
      const idleStart=await page.evaluate(()=>window.timberbimDiagnostics.snapshot().renderer.render_count);
      await page.waitForTimeout(2000);
      const after={metrics:await page.evaluate(()=>window.timberbimDiagnostics.snapshot()),heap:await heap()};
      const idleFrames=after.metrics.renderer.render_count-idleStart;
      assert.equal(idleFrames,0,'a settled model must not keep rendering while idle');
      for(const key of ['build_ms','selection_ms','ray_pick_ms'])after.metrics.timings[key]=operationTimings[key];
      await page.evaluate(()=>{window.timberbimDiagnostics.reset();window.timberbimDiagnostics.rotate(true);});
      const rotationStart=await page.evaluate(()=>window.timberbimDiagnostics.snapshot());
      await page.waitForTimeout(2000);
      const rotation=await page.evaluate(()=>window.timberbimDiagnostics.snapshot());
      assert.ok(rotation.renderer.render_count>rotationStart.renderer.render_count,'auto-rotation must keep rendering');
      assert.notDeepEqual(rotation.camera.position,rotationStart.camera.position,'auto-rotation must move the camera');
      await page.evaluate(()=>window.timberbimDiagnostics.rotate(false));
      await page.waitForFunction(()=>!window.timberbimDiagnostics.snapshot().render_pending);
      assert.deepEqual(errors,[]);assert.equal(after.metrics.model_member_count,reference.member_count);
      assert.equal(after.metrics.renderer.explicit_buffer_balance,before.metrics.renderer.explicit_buffer_balance,'same-model rendered rebuilds must release their replaced instance buffers');
      report.fixtures.push({id:fixture,viewport,loopback_transfer:transfer,rebuild_count:repeats,idle_frame_sample_ms:2000,idle_render_count:idleFrames,
        auto_rotation_sample_ms:2000,auto_rotation_render_count:rotation.renderer.render_count-rotationStart.renderer.render_count,
        auto_rotation_timings:rotation.timings,ray_pick_attempts:selected.length,ray_pick_hits:hits,before,after});
      await page.screenshot({path:join(runtime,`${fixture}-${viewport.width}.png`)});
      await context.close();console.log(`Profiled ${fixture} at ${viewport.width}px: ${reference.member_count} members.`);
    }
  }
  if(output){const target=resolve(output);await mkdir(dirname(target),{recursive:true});await writeFile(target,JSON.stringify(report,null,2)+'\n');console.log(`Measurements written to ${target}`);}
  else console.log(JSON.stringify(report,null,2));
}catch(error){console.error('Backend:',logs);throw error;}
finally{
  await browser?.close();
  if(service?.exitCode===null){service.kill('SIGTERM');await once(service,'exit');}
  await rm(runtime,{recursive:true,force:true});
}
