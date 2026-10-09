// UXB-06F: supplementary contract evidence only; not a logged-in browser/User E2E.
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,rmSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,menu;
before(async()=>{
  scratch=mkdtempSync(join(root,'node_modules','.uxb-menu-evidence-'));
  const outfile=join(scratch,'evidence.mjs');
  await build({entryPoints:[join(root,'src','uxb-menu-evidence.ts')],outfile,
    bundle:true,platform:'node',format:'esm',logLevel:'silent'});
  menu=await import(pathToFileURL(outfile).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

test('each Core collection menu recognizes real observed emptiness, not a broken response',()=>{
  for(const route of ['hosts','services','policies','enrollments','hygiene','jobs','audit','revisions','views','users','service-accounts','webhooks']){
    const empty={items:[]};
    assert.equal(menu.requireObservedMenuPayload(route,empty),empty,route);
    const populated={items:[{id:'observed'}]};
    assert.equal(menu.requireObservedMenuPayload(route,populated),populated,route);
    for(const bad of [null,undefined,{}, {items:null},{items:{}},{items:''},{items:false},
      {items:0},{items:[null]},{items:['invalid']},{items:[[]]},{items:[],next_cursor:42},
      {error:'Core unavailable'},[]]){
      assert.throws(()=>menu.requireObservedMenuPayload(route,bad),/Core|UNKNOWN/,route);
    }
  }
});
test('structurally required non-item Core pages remain UNKNOWN without evidence',()=>{
  for(const [route,valid,broken] of [
    ['doctor',{checks:[]},{checks:null}],
    ['versions',{hosts:[]},{hosts:'unknown'}],
    ['overview',{overview:{managed_hosts:{total:0}}},{overview:null}],
  ]){
    assert.equal(menu.requireObservedMenuPayload(route,valid),valid);
    assert.throws(()=>menu.requireObservedMenuPayload(route,broken),/Core|UNKNOWN/);
  }
});
test('Core pagination is visible and local filters never imply a complete list',()=>{
  for(const response of [null,undefined,{items:[]},{items:[],next_cursor:null},
    {items:[],next_cursor:''},{items:[],next_cursor:7}]){
    assert.equal(menu.isPartialCorePage(response),false);
  }
  const paged={items:[{id:'loaded'}],next_cursor:'opaque-core-cursor'};
  assert.equal(menu.isPartialCorePage(paged),true);
  assert.equal(menu.requireObservedMenuPayload('hosts',paged),paged);
  assert.equal(menu.requireObservedMenuPayload('policies',paged),paged);
});
test('Managed Host and Remote Service pagination accepts only matching observed Core pages',()=>{
  const cursor='observed-opaque-core-page';
  for(const [route,resource_type] of [
    ['hosts','managed-host'],['services','remote-service']
  ]){
    const page={resource_type,limit:100,items:[{id:'item-101',name:'Observed'}],next_cursor:null};
    assert.equal(menu.requireObservedInventoryContinuation(route,page,cursor,100),page);
    for(const wrong of [
      {...page,resource_type:route==='hosts'?'remote-service':'managed-host'},
      {...page,limit:50},
      {...page,items:[{id:''}]},
      {...page,items:[{id:17}]},
      {...page,items:Array.from({length:101},(_,i)=>({id:String(i)}))},
      {...page,next_cursor:cursor},
      {...page,items:null},
      {error:'Core unreachable'},
    ]){
      assert.throws(()=>menu.requireObservedInventoryContinuation(route,wrong,cursor,100),
        /Core|UNKNOWN/,route);
    }
  }
});

test('Audit keyset backward and forward pagination uses opaque observed Core cursors only',()=>{
  const start={cursor:'',history:[]};
  assert.deepEqual(menu.selectMenuPage(start,'cursor-page-2','older'),
    {cursor:'cursor-page-2',history:['']});
  const page2=menu.selectMenuPage(start,'cursor-page-2','older');
  assert.deepEqual(menu.selectMenuPage(page2,'cursor-page-3','older'),
    {cursor:'cursor-page-3',history:['','cursor-page-2']});
  const page3=menu.selectMenuPage(page2,'cursor-page-3','older');
  assert.deepEqual(menu.selectMenuPage(page3,null,'newer'),page2);
  assert.deepEqual(menu.selectMenuPage(page2,null,'newer'),start);
  assert.deepEqual(menu.selectMenuPage(page3,null,'reset'),start);
  assert.equal(menu.selectMenuPage(start,null,'newer'),null);
  for(const invalid of [null,undefined,{},'',false,'cursor-page-2']){
    assert.equal(menu.selectMenuPage(page2,invalid,'older'),null);
  }
});
test('large Remote policy family cannot hide observed Internet or AI rules',()=>{
  const corePage=(plane,ids,limit=2)=>({plane,limit,
    items:ids.map(id=>({id,plane,name:id}))});
  const pages=[
    corePage('remote',['r-1','r-2']),
    corePage('internet',['i-1']),
    corePage('ai',['a-1'])
  ];
  const observed=menu.combineObservedPolicyPlanes(pages,2);
  assert.deepEqual(observed.items.map(row=>row.id),['r-1','r-2','i-1','a-1']);
  assert.deepEqual(observed.possibly_truncated_planes,['remote']);
  assert.deepEqual(observed.next_cursor_by_plane,{remote:null,internet:null,ai:null});
  assert.deepEqual(menu.combineObservedPolicyPlanes(pages.map(page=>({...page,items:[]})),2),
    {items:[],possibly_truncated_planes:[],next_cursor_by_plane:{remote:null,internet:null,ai:null}});
  const withCursors=menu.combineObservedPolicyPlanes(
    pages.map((page,i)=>({...page,next_cursor:i===0?'opaque-next-page':null})),2);
  assert.equal(withCursors.next_cursor_by_plane.remote,'opaque-next-page');
  assert.deepEqual(withCursors.possibly_truncated_planes,['remote']);
  const lastPage=menu.combineObservedPolicyPlanes(
    pages.map(page=>({...page,next_cursor:null})),2);
  assert.deepEqual(lastPage.possibly_truncated_planes,[]);
  for(const bad of [
    pages.slice(0,2),null,[],[pages[1],pages[0],pages[2]],
    [pages[0],{plane:'internet',limit:2,items:null},pages[2]],
    [pages[0],{...pages[1],items:[{id:'wrong',plane:'remote'}]},pages[2]],
    [pages[0],{...pages[1],limit:1},pages[2]],
    [pages[0],{...pages[1],items:[{plane:'internet'},{plane:'internet'},{plane:'internet'}]},pages[2]],
  ]){
    assert.throws(()=>menu.combineObservedPolicyPlanes(bad,2),/Core|UNKNOWN/);
  }
});
test('partial Objects inventory remains available for its existing explicit UNKNOWN warning',()=>{
  // ObjectsWorkspace itself distinguishes incomplete resources from a valid empty list.
  for(const response of [{resources:{}},{resources:{'network-object':{items:[]}}}]){
    assert.equal(menu.requireObservedMenuPayload('objects',response),response);
  }
});
