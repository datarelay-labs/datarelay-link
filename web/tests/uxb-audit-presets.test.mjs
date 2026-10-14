// G-08 — original Audit UTC time shortcuts (source and pure boundary evidence).
// These tests are not a claim of authenticated desktop/mobile Browser E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {build} from 'esbuild';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drl3-audit-presets-'));
let presets;
try{
 const output=join(scratch,'presets.mjs');
 await build({entryPoints:[join(root,'src','uxb-audit-presets.ts')],
   outfile:output,platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 presets=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test('G-08 quick presets use one absolute UTC click instant with second precision across rollover and DST',()=>{
 const cases=[
  [1,'2026-11-01T00:30:05.876Z','2026-10-31T23:30:05Z','2026-11-01T00:30:05Z'],
  [3,'2026-03-08T09:30:00.000Z','2026-03-08T06:30:00Z','2026-03-08T09:30:00Z'],
  [24,'2026-03-01T00:10:00.999Z','2026-02-28T00:10:00Z','2026-03-01T00:10:00Z'],
  [168,'2026-01-01T02:03:04.999Z','2025-12-25T02:03:04Z','2026-01-01T02:03:04Z']
 ];
 for(const [hours,stamp,start,end] of cases){
  const actual=presets.auditUtcPresetRange(hours,Date.parse(stamp));
  assert.deepEqual(actual,{start,end},String(hours));
  assert.equal(Date.parse(actual.end)-Date.parse(actual.start),hours*3600000);
 }
});
test('G-08 denies unsupported durations, malformed clocks, non-integer and out-of-range anchors',()=>{
 const now=Date.parse('2026-10-11T12:34:56Z');
 for(const hours of [0,2,7,12,169,1.5,-1,NaN,Infinity,'1',null,{},true])
  assert.equal(presets.auditUtcPresetRange(hours,now),null,JSON.stringify(hours));
 for(const anchor of [null,undefined,'2026-10-11',NaN,Infinity,-Infinity,-1,0,
    1.5,Number.MAX_SAFE_INTEGER,8640000000000001])
  assert.equal(presets.auditUtcPresetRange(1,anchor),null,String(anchor));
});
test('G-08 Audit controls are keyboard buttons, edit-only, responsive, and never auto-query Core',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const audit=source.split('function AuditExplorer(',2)[1]?.split('function AgentRolloutPreviewPanel(',1)[0]||'';
 assert.match(audit,/function chooseAuditUtcPreset\(hours:number\)/);
 const handler=audit.match(/function chooseAuditUtcPreset\(hours:number\)\{([\s\S]*?)\n  \}/)?.[1]||'';
 assert.match(handler,/auditUtcPresetRange\(hours,Date\.now\(\)\)/);
 assert.equal((handler.match(/Date\.now\(\)/g)||[]).length,1);
 assert.match(handler,/setStart\(range\.start\)/);
 assert.match(handler,/setEnd\(range\.end\)/);
 assert.doesNotMatch(handler,/\b(?:api|load|exportAudit|configureRetention|runRetention)\s*\(/);
 assert.match(audit,/role="group" aria-label="Audit UTC time range shortcuts"/);
 for(const [hours,text] of [[1,'Last 1h'],[3,'Last 3h'],[24,'Last 24h'],[168,'Last 7d']]){
  assert.match(audit,new RegExp('type="button"[^>]*onClick=\\{\\(\\)=>chooseAuditUtcPreset\\('+hours+'\\)\\}[^>]*>'+text+'<\\/button>'));
 }
 assert.match(audit,/auditFiltersEdited\?null:/);
 assert.match(audit,/Filters changed since the loaded Audit page\. Select Search audit to apply them/);
 assert.match(audit,/onClick=\{\(\)=>load\(\)\}>Search audit/);
 assert.match(audit,/observedAuditAppliedFilters\(auditFilterKey\)/);
 const css=readFileSync(join(root,'dist','styles.css'),'utf8');
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
 assert.match(css,/@media\(max-width:760px\)\{[^}]*\.dr-form-grid\.two,/);
});
