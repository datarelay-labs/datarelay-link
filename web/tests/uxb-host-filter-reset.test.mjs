// G-12: Host-only one-click reset of three local display facets.
// Contract tests do not replace real authenticated browser/keyboard User E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-host-reset-"));
let mod;
try{
 const output=join(scratch,"reset.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-filter-reset.ts")],
   outfile:output,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 mod=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("G-12 clear action is visible only if any of three display facets is active",()=>{
 const need=mod.hostDisplayFilterResetAvailable;
 assert.equal(need("","all","all"),false);
 assert.equal(need("   ","all","all"),false);
 assert.equal(need("hostname:server","all","all"),true);
 assert.equal(need("","APPROVED","all"),true);
 assert.equal(need("","all","connected"),true);
 assert.equal(need("","all","unknown"),true);
 assert.equal(need("name:prod","QUARANTINED","disconnected"),true);
 assert.equal(need("","all","all"),false);
});
test("G-12 malformed local state cannot hide the reset affordance",()=>{
 const need=mod.hostDisplayFilterResetAvailable;
 for(const v of [null,undefined,{},[],123,true]){
  assert.equal(need(v,"all","all"),true,String(v));
  assert.equal(need("","all",v),true,String(v));
  assert.equal(need("",v,"all"),true,String(v));
 }
});
test("G-12 Web reset only clears local Host filters, not Core inventory, identity, search or saved views",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const host=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(host,/const hostFiltersActive=isHost&&hostDisplayFilterResetAvailable\(filter,admissionFilter,connectionFilter\)/);
 const handler=host.match(/function clearHostDisplayFilters\(\)\{([\s\S]*?)\n  \}/)?.[1]||"";
 for(const c of [/setFilter\(""\)/, /setAdmissionFilter\("all"\)/, /setConnectionFilter\("all"\)/])assert.match(handler,c);
 assert.doesNotMatch(handler,/\b(?:api|fetch|load|setLoaded|setCursor|setPagesLoaded|onNavigate|localStorage|saveDraftForResource|clearSession)\s*\(/);
 assert.match(host,/\{isHost&&hostFiltersActive&&<button type="button" className="secondary"/);
 assert.match(host,/onClick=\{clearHostDisplayFilters\}>Clear Host filters<\/button>/);
 assert.match(host,/Existing loaded Core inventory and Saved Views remain unchanged/);
 assert.match(host,/Connection quick filter is not saved/);
 assert.match(host,/Partial Core inventory/);
 assert.match(host,/Load more Managed Hosts/);
 assert.match(host,/aria-label="Filter loaded Host connection state"/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
