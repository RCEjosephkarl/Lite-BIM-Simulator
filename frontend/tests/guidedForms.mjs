import assert from 'node:assert/strict';

/** Use a fresh browser profile so existing drafts cannot mask form defaults. */
export async function checkGuidedForms(browser,url,projectId,errors){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const requests=[];page.on('request',request=>{if(new URL(request.url()).pathname==='/api/manual/wall-frame/preview')requests.push(request);});
  try {
    await page.goto(`${url}/?project_id=${projectId}&section=wall`);
    await page.locator('#home-status').filter({hasText:'revision'}).waitFor();
    await page.getByRole('button',{name:'Pin sidebar',exact:true}).click();
    assert.equal(await page.locator('#wall-form fieldset').count(),3);
    assert.ok((await page.locator('#wall-derived').textContent()).includes('6000.0 mm'));
    assert.ok(await page.locator('#wall-form [name=start_x_mm]').evaluate(input=>input.labels.length>0));
    await page.locator('#wall-form [name=start_x_mm]').fill('');
    await page.locator('#wall-preview').press('Enter');
    await page.locator('#wall-field-errors').filter({hasText:'Start X (mm) is required'}).waitFor();
    assert.equal(requests.length,0,'blank required coordinates are not submitted as zero');
    assert.equal(await page.locator('#wall-form [name=start_x_mm]').getAttribute('aria-invalid'),'true');
    assert.ok(await page.locator('#wall-form [name=start_x_mm]').evaluate(input=>document.activeElement===input));
    await page.locator('#wall-form [name=start_x_mm]').fill('0');
    await page.locator('#add-opening').click();
    const head=page.locator('#wall-openings [name=head_height_mm]');
    const width=page.locator('#wall-openings [name=width_mm]');
    await head.fill('2200');await page.locator('#wall-preview').press('Enter');
    await page.locator('#wall-field-errors').filter({hasText:'Head must equal sill + clear height (2100 mm)'}).waitFor();
    assert.equal(requests.length,0);assert.equal(await head.getAttribute('aria-invalid'),'true');
    assert.ok(await head.evaluate(input=>document.getElementById(input.getAttribute('aria-describedby')).textContent.includes('2100 mm')));
    await head.fill('');await width.fill('');
    await page.reload();await page.locator('#home-status').filter({hasText:'revision'}).waitFor();
    assert.equal(await head.inputValue(),'');assert.equal(await width.inputValue(),'','unfinished opening width survives reload');
    const draft=await page.evaluate(projectId=>JSON.parse(localStorage.getItem(`timberbim.manualWallDraft.${projectId}`)),projectId);
    assert.equal(draft.schema_version,2);assert.equal(draft.openings[0].width_mm,'');
    await width.fill('0');await page.locator('#wall-preview').press('Enter');
    await page.locator('#wall-field-errors').filter({hasText:'Input should be greater than 0'}).waitFor();
    assert.match(await page.locator('#wall-field-errors').textContent(),/Request reference: [0-9a-f]{32}/,'server field errors retain a support reference');
    assert.equal(await width.getAttribute('aria-invalid'),'true','server opening path reaches the correct field');
    assert.ok(await width.evaluate(input=>document.activeElement===input));
    await width.fill('1200');await page.locator('#wall-form [name=nog_spacing_mm]').fill('50');
    await page.locator('#wall-form [name=start_x_mm]').fill('0.5');await page.locator('#wall-form [name=end_x_mm]').fill('6000.5');
    await page.locator('#wall-preview').press('Enter');
    await page.locator('#wall-review-stage').filter({hasText:'Validated preview is ready'}).waitFor();
    assert.ok(await page.locator('#wall-field-errors').isHidden());
    assert.ok(!(await page.locator('#wall-commit').isDisabled()),'valid fractional coordinates and positive optional nog spacing remain available');
    await width.fill('1100');assert.ok(await page.locator('#wall-commit').isDisabled());
    assert.ok((await page.locator('#wall-review-stage').textContent()).includes('previous preview can no longer be saved'));
    await width.fill('1200');await page.locator('#wall-preview').press('Enter');
    await page.waitForFunction(()=>!document.querySelector('#wall-commit').disabled);
    let lost=false;
    await page.route('**/api/manual/wall-frame/commit?*',async route=>{
      if(!lost){lost=true;await route.fetch();await route.abort('failed');}else await route.continue();
    });
    await page.locator('#wall-commit').press('Enter');
    await page.locator('#wall-review-stage').filter({hasText:'retained for a retry'}).waitFor();
    assert.ok(!(await page.locator('#wall-commit').isDisabled()));
    await page.locator('#wall-commit').press('Enter');
    await page.locator('#wall-review-stage').filter({hasText:"Saved to this home's current revision"}).waitFor();
    assert.ok(await page.locator('#wall-field-errors').isHidden(),'success clears transport errors');
    const model=await(await fetch(`${url}/api/model?project_id=${projectId}`)).json();
    assert.equal(new Set(model.elements.filter(m=>m.source==='manual_wall').map(m=>m.source_id)).size,1,'lost-reply retry creates one assembly');
    await page.getByRole('button',{name:'Manual Truss Input',exact:true}).click();
    assert.equal(await page.locator('#truss-form fieldset').count(),4);
    await page.locator('#truss-form [name=quantity]').fill('3');
    assert.ok((await page.locator('#truss-derived').textContent()).includes('1800.0 mm'));
    await page.locator('#truss-form [name=truss_type]').selectOption('custom');
    const nodes=page.locator('#truss-form [name=nodes_csv]'),members=page.locator('#truss-form [name=members_csv]');
    const initialNodes=await nodes.inputValue(),initialMembers=await members.inputValue();
    await nodes.fill('id,x,y\nBAD,NaN,0');await page.locator('#truss-preview').press('Enter');
    await page.locator('#truss-field-errors').filter({hasText:'finite numbers'}).waitFor();
    assert.equal(await nodes.getAttribute('aria-invalid'),'true');
    await nodes.fill(initialNodes);await members.fill('L,C,top_chord,bad-size,SG8\nC,R,top_chord,140x45,SG8\nL,R,bottom_chord,90x45,SG8\nB,C,king_post,90x45,SG8');
    await page.locator('#truss-preview').press('Enter');await page.locator('#truss-field-errors').waitFor();
    assert.equal(await members.getAttribute('aria-invalid'),'true','server member size errors reach the custom graph input');
    await members.fill(initialMembers);await page.locator('#truss-form [name=truss_type]').selectOption('common');
    await page.locator('#truss-form [name=pitch_deg]').fill('25.5');await page.locator('#truss-preview').press('Enter');
    await page.locator('#truss-review-stage').filter({hasText:'Validated preview is ready'}).waitFor();
    await page.getByRole('button',{name:'Model browser',exact:true}).click();await page.locator('#model-search').fill('Manual truss');
    await page.locator('.model-tree-item').first().press('Enter');await page.locator('#member-inspector').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('section'),'truss','inspection leaves the active form open');
    assert.equal(await page.locator('#truss-form [name=pitch_deg]').inputValue(),'25.5');
    await page.locator('#preview-cancel').click();assert.ok(await page.locator('#truss-commit').isDisabled());
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Manual Wall Frame Input',exact:true}).click();
    assert.ok(await page.locator('#model-browser').isHidden());assert.ok(await page.locator('#member-inspector').isHidden(),'opening a mobile form frees the upper canvas');
    await head.fill('2200');await page.locator('#wall-preview').press('Enter');
    await page.locator('#wall-field-errors').filter({hasText:'Head must equal'}).waitFor();
    assert.ok(await head.evaluate(input=>document.activeElement===input));
    const field=await head.boundingBox();assert.ok(field.x>=64&&field.x+field.width<=390&&field.y>=844*.44&&field.y+field.height<=844,'error field is reachable within the mobile sheet');
    await page.screenshot({path:'/tmp/lite-bim-guided-form-review.png'});
    await page.getByRole('button',{name:'Close panel',exact:true}).click();assert.ok(await page.locator('.sidebar-content').isHidden());
    console.log('Guided forms checked: field groups, inline/native/server errors, raw opening recovery, derived geometry, preserved decimal ranges, keyboard preview, lost-reply retry and mobile focus.');
  }catch(error){
    for(const selector of ['#wall-field-errors','#wall-review-stage','#truss-field-errors','#truss-review-stage'])
      console.error(selector,await page.locator(selector).textContent().catch(()=>''));
    await page.screenshot({path:'/tmp/lite-bim-guided-form-failure.png'}).catch(()=>{});
    throw error;
  }finally{await context.close();}
}
