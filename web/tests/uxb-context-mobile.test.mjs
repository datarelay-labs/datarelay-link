// Source-level responsive contract only, not 320px/375px real browser acceptance.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const css=readFileSync(join(root,'dist','styles.css'),'utf8');
const contextRule=css.match(/^\.dr-uxb-context\{([^}]*)\}/m)?.[1]||'';

test('bounded Audit and Access context can wrap 160-character Core resource IDs on narrow screens',()=>{
  assert.match(contextRule,/\bmin-width\s*:\s*0\b/);
  assert.match(contextRule,/\boverflow-wrap\s*:\s*anywhere\b/);
});
test('context stays a reusable DRLink-owned style, with existing narrow workspace support',()=>{
  assert.match(css,/\.dr-uxb-context strong\{font-size:/);
  assert.match(css,/@media\(max-width:560px\)\{[^\n]*\.dr-workspace\{padding:12px\}/);
});

test('UX-7 Core evidence summary stays readable and touch-accessible at 320/375px source breakpoints',()=>{
 const base=[...css.matchAll(/^\.dr-uxb-evidence-strip\{([^}]*)\}/gm)].at(-1)?.[1]||'';
 assert.match(base,/\bflex-wrap:wrap\b/);
 assert.match(base,/\bmin-width:0\b/);
 const text=css.match(/^\.dr-uxb-evidence-strip>span,\.dr-uxb-evidence-strip>small\{([^}]*)\}/m)?.[1]||'';
 assert.match(text,/\boverflow-wrap:anywhere\b/);
 const btn=css.match(/^\.dr-uxb-evidence-strip>button\{([^}]*)\}/m)?.[1]||'';
 assert.match(btn,/\bmin-height:40px\b/);
 assert.match(css,/@media\(max-width:560px\)\{\.dr-uxb-evidence-strip\{display:grid;grid-template-columns:minmax\(0,1fr\)/);
 assert.match(css,/\.dr-uxb-evidence-strip>button\{width:100%;margin-left:0\}\}/);
});

test('UX-4 actionable Core attention rows wrap safely at 320px and remain keyboard accessible',()=>{
 const row=css.match(/^\.dr-uxb-attention-list>li\{([^}]*)\}/m)?.[1]||'';
 assert.match(row,/\bmin-width:0\b/);
 assert.match(row,/\bgrid-template-columns:minmax\(0,1fr\) auto\b/);
 const label=css.match(/^\.dr-uxb-attention-list>li strong\{([^}]*)\}/m)?.[1]||'';
 assert.match(label,/\boverflow-wrap:anywhere\b/);
 const action=css.match(/^\.dr-uxb-attention-list>li button\{([^}]*)\}/m)?.[1]||'';
 assert.match(action,/\bmin-height:40px\b/);
 assert.match(css,/@media\(max-width:560px\)\{\.dr-uxb-attention-list>li\{grid-template-columns:minmax\(0,1fr\)/);
 assert.match(css,/\.dr-uxb-attention-list>li button\{width:100%\}\}/);
});

test("UXR-5.1/5.5 redesigned workflow targets and generic detail dialogs use shared readable focus contract",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(main,/function useDialogFocusTrap/);
 assert.match(main,/e\.key==="Escape"/);assert.match(main,/e\.key!=="Tab"/);
 assert.match(main,/previous\.focus\(\{preventScroll:true\}\)/);
 assert.match(main,/ref=\{detailRef\} className="dr-detail-drawer"/);
 assert.equal((main.match(/useDialogFocusTrap\(\!\!selected/g)||[]).length,3);
 assert.match(css,/\.dr-page-intro h2,.dr-server-welcome h2\{font-size:24px/);
 assert.match(css,/button\.primary,button\.secondary,button\.danger\)\{min-height:44px\}/);
 assert.match(css,/\.dr-detail-drawer:focus-visible/);
});


test("UXR-5.2 nonessential Core implementation evidence uses one accessible Technical details disclosure while critical warnings stay visible",()=>{
 const files=["p0-enrollment.tsx","p0-access-policy.tsx","uxb-remote-service.tsx","main.tsx"].map(name=>readFileSync(join(root,"src",name),"utf8")).join("\n");
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(files,/Technical details · approval impact/);
 assert.match(files,/Technical details · exact Core trace/);
 assert.match(files,/Technical details · Core preview and graph overlay/);
 assert.match(files,/Technical details · owning Host and expected work/);
 assert.match(files,/Technical details · bounded Core job evidence/);
 assert.match(files,/Technical details · bounded Core health facts/);
 assert.match(files,/Delete is destructive/);
 assert.match(files,/Core impact model is truncated|impact model is truncated/);
 assert.match(files,/Required tests:/);
 assert.match(css,/\.dr-technical-details>summary\{min-height:44px/);
 assert.match(css,/\.dr-technical-details>summary:focus-visible/);
});
