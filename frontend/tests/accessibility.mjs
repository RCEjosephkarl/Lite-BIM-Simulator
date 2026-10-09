import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';

const panels=[['specs','Building Specs'],['bom','BOM'],['pricing','Pricing'],['imports','Imports / Drawing Plans'],
  ['wall','Manual Wall Frame Input'],['truss','Manual Truss Input'],['settings','Settings / Warnings']];
const interactiveRoles=new Set(['button','checkbox','combobox','textbox','spinbutton','searchbox','link','DisclosureTriangle']);

/** Browser accessibility tree and real Tab traversal, across every essential page. */
export async function checkAccessibility(browser,url,projectId,errors){
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const cdp=await context.newCDPSession(page);
  const reportPath=process.env.TIMBERBIM_ACCESSIBILITY_REPORT&&resolve(process.env.TIMBERBIM_ACCESSIBILITY_REPORT);
  const screenshots=reportPath?reportPath.replace(/\.json$/,'')+'-screenshots':null;
  const record={assessment_schema_version:1,recorded_at:new Date().toISOString(),
    application_version:(await readFile(new URL('../../VERSION',import.meta.url),'utf8')).trim(),
    chromium:browser.version(),reduced_motion:'reduce',cases:[],result:'running'};
  if(reportPath)await mkdir(screenshots,{recursive:true});
  const audit=async(label)=>{
    const {nodes}=await cdp.send('Accessibility.getFullAXTree');
    const unnamed=nodes.filter(n=>!n.ignored&&interactiveRoles.has(n.role?.value)&&!n.name?.value?.trim());
    assert.deepEqual(unnamed.map(n=>({role:n.role.value,node:n.backendDOMNodeId})),[],`${label}: all exposed actions have accessible names`);
    const broken=await page.evaluate(()=>{
      const issues=[],ids=new Set();
      for(const el of document.querySelectorAll('[id]')){
        if(ids.has(el.id))issues.push(`Duplicate ID ${el.id}`);ids.add(el.id);
      }
      for(const el of document.querySelectorAll('[aria-controls],[aria-labelledby],[aria-describedby]'))
        for(const attr of ['aria-controls','aria-labelledby','aria-describedby'])
          for(const id of (el.getAttribute(attr)||'').split(/\s+/).filter(Boolean))
            if(!document.getElementById(id))issues.push(`${el.id||el.tagName}: ${attr} points to missing ${id}`);
      return issues;
    });
    assert.deepEqual(broken,[],`${label}: accessible references are intact`);
    const tables=nodes.filter(n=>!n.ignored&&n.role?.value==='table');
    assert.ok(tables.every(n=>n.name?.value?.trim()),`${label}: tables have accessible names`);
    record.cases.push({label,viewport:page.viewportSize(),named_controls:nodes.filter(n=>!n.ignored&&interactiveRoles.has(n.role?.value)).length,
      table_names:tables.map(n=>n.name.value),aria_references_intact:true});
  };
  const tabCycle=async(label)=>{
    const expected=await page.evaluate(()=>{
      const controls=[...document.querySelectorAll('button,input,select,textarea,summary,a[href],[contenteditable=true],[tabindex]')];
      controls.forEach((el,i)=>el.dataset.auditTab=String(i));
      return controls.filter(el=>!el.disabled&&el.tabIndex>=0&&el.checkVisibility({opacityProperty:true,visibilityProperty:true})
        &&el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0).map(el=>el.dataset.auditTab);
    });
    const start=page.locator('[data-section="specs"]');await start.focus();
    const first=await start.getAttribute('data-audit-tab'),visited=new Set([first]);
    let wrapped=false;
    for(let i=0;i<expected.length+5;i++){
      await page.keyboard.press('Tab');
      const key=await page.evaluate(()=>document.activeElement?.getAttribute('data-audit-tab'));
      if(key===first){wrapped=true;break;}if(key)visited.add(key);
    }
    assert.ok(wrapped,`${label}: Tab leaves every control and wraps without a trap`);
    const missing=await page.evaluate(keys=>keys.map(key=>{
      const el=document.querySelector(`[data-audit-tab="${key}"]`);
      return {key,id:el.id,name:el.getAttribute('aria-label')||el.textContent||el.name};
    }),expected.filter(key=>!visited.has(key)));
    assert.deepEqual(missing,[],`${label}: every exposed enabled control is reachable with Tab`);
    const current=record.cases.findLast(item=>item.label===label);
    current.enabled_tab_targets=expected.length;current.reached_tab_targets=visited.size;current.tab_wrapped=true;
    const labels=await page.locator('.nav-button:focus-visible .nav-label').boundingBox();
    const panel=await page.locator('.sidebar-content').boundingBox();
    if(labels&&panel)assert.ok(labels.x+labels.width<=panel.x||labels.x>=panel.x+panel.width
      ||labels.y+labels.height<=panel.y||labels.y>=panel.y+panel.height,`${label}: navigation label does not cover panel content`);
    await page.evaluate(()=>document.querySelectorAll('[data-audit-tab]').forEach(el=>delete el.dataset.auditTab));
  };
  const capture=async(label)=>{
    if(!reportPath)return;
    const prefix=label.replace(/[^a-z0-9]+/gi,'-').toLowerCase();
    for(const position of ['top','bottom']){
      await page.locator('.sidebar-content').evaluate((el,position)=>el.scrollTop=position==='top'?0:el.scrollHeight,position);
      await page.screenshot({path:join(screenshots,`${prefix}-${position}.png`)});
    }
    await page.locator('.sidebar-content').evaluate(el=>el.scrollTop=0);
  };
  try{
    await page.goto(`${url}/?project_id=${projectId}`);
    record.frontend_bundles=await page.evaluate(()=>[...document.scripts].filter(script=>script.src).map(script=>new URL(script.src).pathname));
    await page.locator('#home-status').filter({hasText:'revision'}).waitFor();
    await page.getByRole('button',{name:'Pin sidebar',exact:true}).click();
    for(const [id,name] of panels){
      await page.getByRole('button',{name,exact:true}).press('Enter');
      assert.equal(await page.locator(`[data-section="${id}"]`).getAttribute('aria-current'),'page');
      assert.equal(await page.locator(`[data-section="${id}"]`).getAttribute('aria-expanded'),'true');
      if(id==='pricing')await page.locator('.price-override').first().waitFor();
      if(id==='wall')await page.locator('#add-opening').press('Enter');
      if(id==='truss')await page.locator('#truss-form [name="truss_type"]').selectOption('custom');
      if(id==='imports'){
        await page.locator('#home-editor-details summary').press('Enter');
        await page.locator('#csv-file').setInputFiles({name:'accessible.csv',mimeType:'text/csv',buffer:Buffer.from(
          'type,level,segment_id,label,start_x_mm,start_z_mm,end_x_mm,end_z_mm,height_mm\nwall,1,ACCESS,Accessible wall,0,0,3600,0,2535\n')});
        await page.locator('#csv-summary').filter({hasText:'0 errors'}).waitFor();
        await page.locator('#csv-review').press('Enter');
        await page.locator('#csv-summary').filter({hasText:'0 errors'}).waitFor();
        await page.locator('#csv-preview').press('Enter');
        await page.waitForFunction(()=>!document.querySelector('#csv-commit').disabled);
        await page.locator('#preview-cancel').press('Enter');
        assert.ok(await page.locator('#csv-commit').isDisabled(),'keyboard cancellation invalidates import readiness');
        record.keyboard_csv_preview_and_cancel=true;
      }
      await audit(`${name} desktop`);await tabCycle(`${name} desktop`);
      await capture(`${name} desktop`);
      console.log(`Accessibility checked: ${name} desktop names, references and Tab reachability.`);
    }
    for(const [id,name] of [['bom','BOM'],['pricing','Pricing']]){
      await page.getByRole('button',{name,exact:true}).press('Enter');
      await page.locator(`#${id}-expand`).press('Enter');await audit(`${name} dialog`);
      const dialog=page.getByRole('dialog',{name,exact:true});assert.ok(await dialog.isVisible());
      const count=await dialog.evaluate(el=>[...el.querySelectorAll('button,input,select,textarea,summary,a[href]')]
        .filter(control=>!control.disabled&&control.tabIndex>=0&&control.checkVisibility()).length);
      for(let i=0;i<count+2;i++){
        await page.keyboard.press('Tab');
        const focus=await page.evaluate(()=>({inside:Boolean(document.activeElement?.closest('dialog[open]')),
          id:document.activeElement?.id,tag:document.activeElement?.tagName,document_focus:document.hasFocus()}));
        // Native dialogs may yield to browser chrome, while the page stays inert.
        const chrome=focus.tag==='BODY'&&!focus.document_focus;
        assert.ok(focus.inside||chrome,`${name} modal Tab ${i+1}/${count+2}: ${JSON.stringify(focus)}`);
        if(chrome)record.cases.at(-1).browser_chrome_boundaries=(record.cases.at(-1).browser_chrome_boundaries??0)+1;
      }
      record.cases.at(-1).modal_tab_checks=count+2;
      await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
      assert.ok(await page.locator(`#${id}-expand`).evaluate(el=>el===document.activeElement));
    }
    await page.setViewportSize({width:390,height:844});
    for(const [id,name] of panels){
      await page.getByRole('button',{name,exact:true}).press('Enter');await audit(`${name} mobile`);await tabCycle(`${name} mobile`);
      await capture(`${name} mobile`);
      const canvas=await page.locator('canvas').boundingBox();const sheet=await page.locator('.sidebar-content').boundingBox();
      assert.ok(canvas.width===390&&canvas.height>0&&canvas.y+canvas.height<=sheet.y+2,`${name}: model and form have separate space`);
      record.cases.at(-1).canvas_bounds=canvas;record.cases.at(-1).sheet_bounds=sheet;
      await page.getByRole('button',{name:'Close panel',exact:true}).press('Enter');
      assert.ok(await page.locator('.sidebar-content').isHidden());
      assert.ok(await page.locator(`[data-section="${id}"]`).evaluate(el=>el===document.activeElement));
      console.log(`Accessibility checked: ${name} mobile names, keyboard and canvas space.`);
    }
    const motion=await page.locator('#sidebar').evaluate(el=>getComputedStyle(el).transitionDuration);
    assert.equal(motion,'0s','reduced-motion preference disables drawer transitions');
    record.text_contrast=await page.evaluate(()=>{
      const panel=document.querySelector('.sidebar-content'),samples=[];
      const luminance=rgb=>rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
        .reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
      const rgba=value=>value.match(/[\d.]+/g).map(Number);
      for(const [name,classes] of [['Secondary notice','notice'],['Inline error','field-error'],['Error message','message error'],
        ['Warning message','message warning'],['Success message','message success']]){
        const sample=document.createElement('span');sample.className=classes;sample.hidden=true;panel.append(sample);
        const text=rgba(getComputedStyle(sample).color).slice(0,3);
        let ancestor=sample,background;
        while(ancestor){const color=rgba(getComputedStyle(ancestor).backgroundColor);if(color.length===3||color[3]===1){background=color.slice(0,3);break;}ancestor=ancestor.parentElement;}
        const a=luminance(text),b=luminance(background);
        samples.push({name,text_rgb:text,background_rgb:background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)});sample.remove();
      }
      return samples;
    });
    assert.ok(record.text_contrast.every(sample=>sample.ratio>=4.5),'core secondary/error/warning/success text has at least 4.5:1 contrast on its solid panel background');
    record.result='passed';record.reduced_motion_transition_duration=motion;
    console.log('Accessibility checks passed for all seven pages, modal focus and reduced motion.');
  }catch(error){record.result='failed';record.failure=error.message;throw error;}
  finally{
    if(reportPath){await mkdir(dirname(reportPath),{recursive:true});await writeFile(reportPath,JSON.stringify(record,null,2)+'\n');}
    await context.close();
  }
}
