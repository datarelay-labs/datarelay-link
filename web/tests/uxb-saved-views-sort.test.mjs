// G-31: original, private Core-loaded Saved Views updated-at time ordering.
// Static pure/SSR/source evidence only; NOT authenticated browser acceptance.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g31-view-sort-"));
let sorter;
try{
 const outfile=join(scratch,"sort.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views-sort.ts")],
  outfile,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 sorter=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

const views=[
 {id:"v-a",name:"Alpha",updated_at:"2026-10-09T12:00:00Z",payload:{filter:"no-access"}},
 {id:"v-b",name:"Bravo",updated_at:"2026-10-12T10:00:00+09:00",secret:"NOT_SEARCHED"},
 {id:"v-c",name:"Charlie",updated_at:"2026-10-12T01:00:00Z",private_key:"NO_READ"},
 {id:"v-d",name:"Delta",updated_at:null},
 {id:"v-e",name:"Echo",updated_at:"2026-02-30T00:00:00Z"},
 {id:"v-f",name:"Foxtrot",updated_at:"2026-10-10T01:00:00Z"}
];
const ids=(mode,items=views)=>sorter.sortLoadedSavedViews(items,mode).map(row=>row.id);

test("G-31 default Core order is exact, preserves original references and does not mutate source",()=>{
 assert.deepEqual(ids("core"),["v-a","v-b","v-c","v-d","v-e","v-f"]);
 const out=sorter.sortLoadedSavedViews(views,"core");
 assert.notEqual(out,views);
 out.forEach((row,i)=>assert.equal(row,views[i]));
 assert.deepEqual(views.map(row=>row.id),ids("core"));
});

test("G-31 local updated ordering respects timezones, stable ties, UNKNOWN always last",()=>{
 assert.deepEqual(ids("updated_desc"),["v-b","v-c","v-f","v-a","v-d","v-e"]);
 assert.deepEqual(ids("updated_asc"),["v-a","v-f","v-b","v-c","v-d","v-e"]);
 const two=views.filter(item=>item.id==="v-a"||item.id==="v-b");
 assert.deepEqual(ids("updated_desc",two),["v-b","v-a"],"never sorts unseen pages");
 assert.equal(sorter.sortLoadedSavedViews(views,"updated_desc")[0],views[1]);
});

test("G-31 invalid modes/untrusted Core shape fail closed; payload and hidden secrets are never consulted",()=>{
 for(const bad of ["","date","recent","updated_asc ","__proto__",null,42,{},[]]){
  assert.equal(sorter.isSavedViewSortMode(bad),false);
  assert.deepEqual(sorter.sortLoadedSavedViews(views,bad),[]);
 }
 for(const bad of [undefined,null,"string",{items:views},Array.from({length:101},()=>({})),[null],[[1]], [true]]){
  assert.deepEqual(sorter.sortLoadedSavedViews(bad,"core"),[]);
 }
 for(const mode of ["core","updated_desc","updated_asc"])assert.equal(sorter.isSavedViewSortMode(mode),true);
 assert.doesNotMatch(JSON.stringify(ids("updated_desc")),/NOT_SEARCHED|NO_READ|no-access/);
 const bad=[{id:"z",name:"Z",updated_at:{"secret":"MUST_NOT_READ"}},
  {id:"a",name:"A",updated_at:"2026-10-01T00:00:00Z"}];
 assert.deepEqual(ids("updated_desc",bad),["a","z"]);
});

test("G-31 native sort is local to already filtered private rows; full collision and 100-name limits untouched",()=>{
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/import \{sortLoadedSavedViews,isSavedViewSortMode,type SavedViewSortMode\} from "\.\/uxb-saved-views-sort"/);
 assert.match(src,/const \[listSort,setListSort\]=useState<SavedViewSortMode>\("core"\)/);
 assert.match(src,/const typedVisibleRows=filterLoadedSavedViewsByType\(visibleRows\.items,targetFacet\)/);
 assert.match(src,/const sortedVisibleRows=sortLoadedSavedViews\(typedVisibleRows,listSort\)/);
 assert.match(src,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(src,/const incompleteNames=rows\.length>=100/);
 assert.match(src,/savedPage\.items\.map\(\(item:any,i:number\)=>/);
 assert.match(src,/aria-label="Sort loaded private saved filters"/);
 assert.ok(src.includes('onChange={e=>{setListSort(isSavedViewSortMode(e.target.value)?e.target.value:"core");setPageIndex(0)}}'));
 for(const [id,label] of [["core","Core order (default)"],["updated_desc","Recently updated"],["updated_asc","Oldest updated"]])
  assert.ok(src.includes('<option value="'+id+'">'+label+'</option>'),label);
 assert.match(src,/Sorting only rearranges loaded operator-private views/);
 assert.match(src,/Missing\/invalid Core updated timestamps remain UNKNOWN/);
 assert.match(src,/Find my saved filters/);
 assert.match(src,/No matching loaded saved filters/);
 assert.match(src,/No saved views yet/);
 assert.doesNotMatch(readFileSync(join(root,"src","uxb-saved-views-sort.ts"),"utf8"),
  /\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
