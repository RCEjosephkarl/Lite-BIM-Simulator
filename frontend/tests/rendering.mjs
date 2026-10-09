import assert from 'node:assert/strict';

/** Real viewer updates must repaint, then settle; rotation and damping remain live. */
export async function checkRendering(browser,url,projectId,errors){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const snapshot=()=>page.evaluate(()=>window.timberbimDiagnostics.snapshot());
  const settle=async()=>{
    await page.waitForFunction(()=>window.timberbimDiagnostics?.snapshot().renderer.render_count>0
      && !window.timberbimDiagnostics.snapshot().render_pending);
  };
  const repaint=async(action)=>{
    await settle();const before=(await snapshot()).renderer.render_count;
    await action();
    await page.waitForFunction(count=>window.timberbimDiagnostics.snapshot().renderer.render_count>count,before);
    await settle();
  };
  try{
    await page.goto(`${url}/?project_id=${projectId}&diagnostics=1`);
    await page.locator('#home-status').filter({hasText:'revision'}).waitFor();await settle();
    const canvas=page.getByRole('region',{name:'3D home model',exact:true});
    const idle=(await snapshot()).renderer.render_count;
    await page.waitForTimeout(400);assert.equal((await snapshot()).renderer.render_count,idle,'idle viewer does not render');
    const initial=await canvas.screenshot();
    await repaint(()=>page.getByRole('button',{name:'Plan',exact:true}).click());
    assert.notDeepEqual(await canvas.screenshot(),initial,'camera changes reach the visible canvas');
    await repaint(()=>page.locator('#view-options summary').first().click().then(()=>page.locator('#view-dimensions').check()));
    assert.equal(await page.locator('.dimension-label').count(),3);
    await repaint(()=>page.locator('#view-section').check());
    await repaint(()=>page.locator('#view-section').uncheck());
    await repaint(()=>page.getByRole('button',{name:'Roof only',exact:true}).click());
    await repaint(()=>page.getByRole('button',{name:'Show all layers',exact:true}).click());
    await page.locator('#view-options summary').first().click();
    await page.getByRole('button',{name:'Pin sidebar',exact:true}).click();
    await page.getByRole('button',{name:'Building Specs',exact:true}).click();await settle();
    const colorBefore=await canvas.screenshot();
    await repaint(()=>page.locator('#mode [data-m="material"]').click());
    assert.notDeepEqual(await canvas.screenshot(),colorBefore,'material colors repaint');
    await repaint(()=>page.getByRole('button',{name:'Model browser',exact:true}).click().then(()=>page.locator('.model-tree-item').first().click()));
    assert.ok(await page.locator('#member-inspector').isVisible());
    await repaint(()=>page.locator('#selection-clear').click());
    const position=(await snapshot()).camera.position;
    const count=(await snapshot()).renderer.render_count;
    await page.locator('#autorotate').check();
    await page.waitForFunction(count=>window.timberbimDiagnostics.snapshot().renderer.render_count>count+3,count);
    assert.notDeepEqual((await snapshot()).camera.position,position,'enabled rotation moves the camera');
    await page.locator('#autorotate').uncheck();await settle();
    await page.getByRole('button',{name:'Unpin sidebar',exact:true}).click();
    await page.mouse.move(1400,950);await settle();
    await repaint(()=>page.setViewportSize({width:1100,height:900}));
    await repaint(()=>canvas.focus().then(()=>page.keyboard.press('ArrowRight')));
    // OrbitControls must keep scheduling its damped motion after pointer release.
    const bounds=await canvas.boundingBox();
    await page.mouse.move(bounds.x+bounds.width*.45,bounds.y+bounds.height*.7);
    await page.mouse.down();await page.mouse.move(bounds.x+bounds.width*.55,bounds.y+bounds.height*.7,{steps:5});
    await page.mouse.up();
    const released=(await snapshot()).renderer.render_count;
    await page.waitForFunction(count=>window.timberbimDiagnostics.snapshot().renderer.render_count>count,released);
    await settle();const stopped=(await snapshot()).renderer.render_count;
    await page.waitForTimeout(400);assert.equal((await snapshot()).renderer.render_count,stopped,'damping eventually settles');
    await repaint(()=>page.evaluate(()=>window.timberbimDiagnostics.rebuild()));
    await repaint(()=>page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange'))));
    console.log('Rendering checks passed: idle stop, visible camera/colors, selection, filters, sections, dimensions, rotation, damping, resize and rebuild.');
  }finally{await context.close();}
}
