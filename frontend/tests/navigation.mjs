import assert from 'node:assert/strict';

/** Independent saved home; no existing user/model/browser state is required. */
export async function checkNavigation(browser,url,errors){
  const request=async(path,body,model,method='POST',proof)=>{
    const query=new URLSearchParams(model?{project_id:model.meta.project.project_id}:{});
    const response=await fetch(`${url}${path}?${query}`,{method,headers:{'Content-Type':'application/json',
      ...(model?{'If-Match':String(model.meta.project.revision)}:{}),
      ...(proof?{'X-Preview-Token':proof.preview_token,'Idempotency-Key':crypto.randomUUID()}:{} )},body:JSON.stringify(body)});
    assert.ok(response.ok,await response.clone().text());return response.json();
  };
  let model=await request('/api/projects',{name:'Navigation regression',geometry_mode:'custom'});
  const examples=await (await fetch(`${url}/api/project/home/examples`)).json();
  const definition=examples.examples.find(e=>e.id==='rectangle').definition;
  let proof=await request('/api/project/home/preview',definition,model);
  model=await request('/api/project/home/commit',definition,model,'PUT',proof);
  const wall={level:1,segment_id:'SAME-WALL',segment_label:'Repeated wall',start_x_mm:0,start_z_mm:12000,end_x_mm:6000,
    end_z_mm:12000,wall_height_mm:2535,thickness_mm:90,stud_spacing_mm:600,stud_size:'90x45',stud_material:'SG8'};
  for(const offset of [12000,16000]){
    const payload={...wall,start_z_mm:offset,end_z_mm:offset};
    proof=await request('/api/manual/wall-frame/preview',payload,model);
    model=(await request('/api/manual/wall-frame/commit',payload,model,'POST',proof)).model;
  }
  const layout={truss_type:'common',span_mm:6000,quantity:260,spacing_mm:100};
  proof=await request('/api/manual/truss/preview',layout,model);
  model=(await request('/api/manual/truss/commit',layout,model,'POST',proof)).model;
  const projectId=model.meta.project.project_id;
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  let releasePending=()=>{};
  try{
    await page.goto(`${url}/?project_id=${projectId}`);
    await page.locator('#home-status').filter({hasText:'revision'}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('project_id'),projectId);
    const canvas=page.getByRole('region',{name:'3D home model',exact:true});
    await page.getByRole('button',{name:'Plan',exact:true}).click();
    const camera=()=>page.locator('#viewport').evaluate(el=>JSON.parse(el.dataset.camera));
    const before=await camera();await canvas.focus();await page.keyboard.press('ArrowRight');
    await page.waitForFunction(target=>JSON.parse(document.querySelector('#viewport').dataset.camera).target[0]>target,before.target[0]);
    assert.ok(await canvas.evaluate(el=>document.activeElement===el));
    const panned=await camera();assert.equal(panned.projection,'orthographic');assert.equal(panned.zoom,before.zoom);
    await page.keyboard.press('+');await page.waitForFunction(zoom=>JSON.parse(document.querySelector('#viewport').dataset.camera).zoom>zoom,panned.zoom);
    const zoomed=await camera();await page.keyboard.press('Shift+ArrowUp');
    await page.waitForFunction(up=>JSON.parse(document.querySelector('#viewport').dataset.camera).up.some((n,i)=>Math.abs(n-up[i])>1e-5),zoomed.up);
    await page.keyboard.press('Home');await page.waitForFunction(()=>JSON.parse(document.querySelector('#viewport').dataset.camera).projection==='perspective');
    await page.getByRole('button',{name:'Model browser',exact:true}).click();
    assert.ok(await page.locator('#model-browser-list summary').filter({hasText:'Level 1'}).count());
    assert.ok(await page.locator('#model-browser-list summary').filter({hasText:'Truss layout'}).count());
    await page.locator('#model-search').fill('manual_truss');
    assert.equal(await page.locator('.model-tree-item').count(),250);
    await page.getByRole('button',{name:'Show 250 more assemblies',exact:true}).press('Enter');
    assert.equal(await page.locator('.model-tree-item').count(),260);
    assert.ok(await page.locator('.model-tree-item').nth(250).evaluate(el=>document.activeElement===el),'paging focuses the first newly available assembly');
    await page.locator('#model-search').fill('Repeated wall');
    assert.equal(await page.locator('.model-tree-item').count(),2,'same wall labels remain separate sources');
    const sources=await page.locator('.model-tree-item').evaluateAll(items=>items.map(el=>JSON.parse(el.dataset.assemblyKey)[2]));
    assert.equal(new Set(sources).size,2);
    const cutDetails=page.locator('#model-browser-list details').filter({has:page.locator(':scope > summary').filter({hasText:'Panels and physical members'})}).first();
    await cutDetails.locator(':scope > summary').click();
    await page.locator('.model-member-item').first().waitFor();
    await page.locator('.model-tree-item').first().press('Enter');
    assert.ok(await page.locator('.model-tree-item[aria-pressed=true]').count());
    const anchor=model.elements.find(e=>e.source==='manual_wall'&&e.source_id===sources[0]);
    const expected=await (await fetch(`${url}/api/bom.json?project_id=${projectId}&member_id=${anchor.id}&revision=${model.meta.project.revision}`)).json();
    expected.rows.sort((a,b)=>a.element.localeCompare(b.element));
    await page.locator('#selection-bom').press('Enter');
    await page.locator('#bom-scope').filter({hasText:anchor.source_id}).waitFor();
    assert.ok((await page.locator('#bom-summary').textContent()).includes(`${expected.rows.reduce((s,r)=>s+r.physical_qty,0)} boards`));
    assert.ok(await page.locator('#bom-scope').evaluate(el=>document.activeElement===el));
    await page.locator('#bom-expand').click();
    await page.locator('[data-bom-locate]').first().press('Enter');
    assert.ok(await page.locator('#bom-workspace').isHidden());
    assert.ok(await canvas.evaluate(el=>document.activeElement===el));
    // View persistence is throttled; assert exact row geometry after settling.
    await page.waitForFunction(({id,count})=>JSON.parse(localStorage.getItem(`timberbim.view.v1.${id}`)).view.isolation?.length===count,
      {id:projectId,count:expected.rows[0].member_ids.length});
    await page.locator('#selection-show-all').click();
    // Scope racing in the same revision: a delayed assembly response cannot replace Whole home.
    let release;const held=new Promise(resolve=>release=resolve);let reached;
    releasePending=release;
    const started=new Promise(resolve=>reached=resolve);
    await page.route('**/api/bom.json?*member_id=*',async route=>{const response=await route.fetch();reached();await held;await route.fulfill({response});});
    await page.locator('#selection-bom').click();await started;
    await page.locator('#bom-clear-scope').click();
    await page.locator('#bom-scope').filter({hasText:'Whole home'}).waitFor();release();
    await page.waitForFunction(()=>!document.querySelector('#bom-summary').textContent.includes('Loading'));
    assert.equal(await page.locator('#bom-scope').textContent(),'Whole home');await page.unroute('**/api/bom.json?*member_id=*');
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'BOM',exact:true}).click();
    await page.locator('[data-bom-locate]').first().press('Enter');
    assert.ok(await page.locator('.sidebar-content').isHidden());assert.ok(await canvas.evaluate(el=>document.activeElement===el));
    const canvasBounds=await canvas.boundingBox(),inspectorBounds=await page.locator('#member-inspector').boundingBox();
    assert.ok(canvasBounds.height>=844*.54&&canvasBounds.width===390,'mobile inspection retains a model viewport');
    assert.ok(inspectorBounds.y>=canvasBounds.y+canvasBounds.height-1,'inspector sheet cannot cover the model canvas');
    await page.keyboard.press('Home');await page.keyboard.press('Tab');assert.ok(!(await canvas.evaluate(el=>document.activeElement===el)),'canvas does not trap Tab');
    await page.screenshot({path:'/tmp/lite-bim-navigation-review.png'});
    console.log('Navigation checked: native hierarchy, source-safe assembly BOM, exact row location, scope races and keyboard/mobile camera/focus.');
  }catch(error){await page.screenshot({path:'/tmp/lite-bim-navigation-failure.png'}).catch(()=>{});throw error;}
  finally{releasePending();await context.close();}
}
