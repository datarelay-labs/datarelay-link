/** WU1: target-first server workspace; presentation only, existing Core authority. */
import React,{useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {hostConnectionState,hostDetailSections,hostInventoryFacts,hostVisibleIdentity} from './uxb-host-detail';
import {filterObservedHosts} from './uxb-host-search';
import {sortLoadedHosts,isHostSortMode,type HostSortMode} from './uxb-host-sort';
import {filterLoadedHostConnections,type HostConnectionFilter} from './uxb-host-connection-filter';
import {isSavedAdmission,saveDraftForResource,type HostAdmission} from './uxb-saved-views';
import {activeHostFilterChips,type HostFilterChipId} from './uxb-host-filter-chips';
import {requireObservedBoundedCorePage,requireObservedInventoryContinuation} from './uxb-menu-evidence';
import {resourceCardSummary} from './uxb-resource-cards';
import {serviceVisibleIdentity,serviceStateLabel} from './uxb-service-detail';

type Row=Record<string,any>;
type Actor={id?:string,role?:string,username?:string}|null;
type Navigate=(id:string,group?:string,context?:any)=>void;
export type ServerManagementAction='metadata'|'admission'|'lifecycle';
type ReadState='ready'|'refreshing'|'stale';
type ServerReturnState={actor:string,filter:string,admission:HostAdmission,connection:HostConnectionFilter,sort:HostSortMode,cards:boolean,reviewOnly:boolean,inspectResourceId:string,detailTab:string,scrollTop:number};
type Props={data:unknown,operator:Actor,api:(path:string,init?:RequestInit)=>Promise<any>,onNavigate?:Navigate,readState?:ReadState,
  initialView?:ServerReturnState|null,onReturnStateChange?:(state:ServerReturnState)=>void,
  onRefresh?:()=>void,initialFilter?:string,initialAdmission?:unknown,initialInspectId?:unknown,
  renderManagement?:(server:Row,action:ServerManagementAction)=>ReactNode};
const validId=(value:unknown):value is string=>typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/.test(value);
const knownActor=(actor:Actor)=>validId(actor?.id)&&['Admin','Operator','Read Only'].includes(actor?.role||'');

/** Return navigation keeps only display choices in this authenticated React shell.
 * Never cache inventory authority, change plans, credentials or mutation payloads.
 */
function observedServerReturnState(value:unknown,actor:Actor):ServerReturnState|null{
  if(!value||typeof value!=='object'||Array.isArray(value)||!knownActor(actor))return null;
  const state=value as Row,key=(actor?.id||'')+':'+(actor?.role||'');
  if(state.actor!==key||typeof state.filter!=='string'||state.filter.length>120||/[\u0000-\u001f\u007f]/.test(state.filter)
    ||!isSavedAdmission(state.admission)||!['all','connected','disconnected','unknown'].includes(state.connection)
    ||!isHostSortMode(state.sort)||typeof state.cards!=='boolean'||typeof state.reviewOnly!=='boolean'
    ||state.inspectResourceId!==''&&!validId(state.inspectResourceId)
    ||!['overview','services','activity','settings'].includes(state.detailTab)
    ||!Number.isSafeInteger(state.scrollTop)||state.scrollTop<0||state.scrollTop>10000000)return null;
  return {actor:key,filter:state.filter,admission:state.admission,connection:state.connection,sort:state.sort,cards:state.cards,
    reviewOnly:state.reviewOnly,inspectResourceId:state.inspectResourceId,detailTab:state.detailTab,scrollTop:state.scrollTop};
}

function observedPage(data:unknown):any|null{
  try{const page=requireObservedBoundedCorePage('hosts',data,'',100);
    // Explicit incomplete/stale markers can never certify a fresh empty list.
    if(page.partial===true||page.truncated===true||page.stale===true||page.complete===false)return null;
    return page;
  }catch{return null}
}
export function serverPageState(data:unknown):'empty'|'populated'|'unavailable'{
  const page=observedPage(data);
  return !page?'unavailable':page.items.length?'populated':'empty';
}
export function serverNextAction(row:Row,actor:Actor):'approval'|'diagnose'|'services'|'details'{
  if(!validId(row?.id)||!knownActor(actor))return 'details';
  if(row.admission_state==='PENDING_APPROVAL')return actor?.role==='Admin'?'approval':'details';
  if(row.admission_state!=='APPROVED')return 'details';
  if(hostConnectionState(row)!=='Connected')return 'diagnose';
  return 'services';
}
function approvalLabel(row:Row):string{
  return row.admission_state==='APPROVED'?'Approved':row.admission_state==='PENDING_APPROVAL'?'Pending approval':row.admission_state==='QUARANTINED'?'Quarantined':'Not reported';
}
const observedLabel=(value:string)=>value==='UNKNOWN'?'Not reported':value;

export function ServerGlyph({kind='server'}:{kind?:string}){
  const props={viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.7,strokeLinecap:'round' as const,strokeLinejoin:'round' as const,'aria-hidden':true as const};
  if(kind==='device')return <svg {...props}><rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8M12 16v5"/></svg>;
  if(kind==='link')return <svg {...props}><path d="m10 13 4-4M8 15l-2 2a4 4 0 0 1-6-5l4-4a4 4 0 0 1 6 0m4 1 2-2a4 4 0 0 1 6 5l-4 4a4 4 0 0 1-6 0" transform="translate(1 -1)"/></svg>;
  if(kind==='search')return <svg {...props}><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg>;
  if(kind==='filter')return <svg {...props}><path d="M4 6h16M7 12h10M10 18h4"/></svg>;
  if(kind==='shield')return <svg {...props}><path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z"/><path d="m8 12 3 3 5-6"/></svg>;
  if(kind==='service')return <svg {...props}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18m-14 4 3 2-3 2m6 0h4"/></svg>;
  return <svg {...props}><rect x="4" y="3" width="16" height="7" rx="2"/><rect x="4" y="14" width="16" height="7" rx="2"/><path d="M8 6.5h.01M8 17.5h.01M12 6.5h4M12 17.5h4"/></svg>;
}
export function RemoteConnectionDiagram(){
  return <div className="dr-wf-route" role="img" aria-label="How remote access works">
    <div><span className="dr-wf-node-icon"><ServerGlyph kind="device"/></span><strong>Your device</strong><small>Only the access you need</small></div>
    <span className="dr-wf-route-edge" aria-hidden="true">→</span>
    <div className="dr-wf-relay-node"><span className="dr-wf-node-icon"><ServerGlyph kind="link"/></span><strong>DataRelay Link</strong><small>Controlled connection</small></div>
    <span className="dr-wf-route-edge" aria-hidden="true">→</span>
    <div><span className="dr-wf-node-icon"><ServerGlyph/></span><strong>Internal server</strong><small>Your selected service</small></div>
  </div>;
}

function RelatedServerServices({server,api,onNavigate}:{server:Row,api:Props['api'],onNavigate?:Navigate}){
  const [rows,setRows]=useState<Row[]>([]),[cursor,setCursor]=useState<string|null>(null);
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[ready,setReady]=useState(false);
  const epoch=useRef(0),pending=useRef(false);
  async function read(next=''){
    if(pending.current)return;
    pending.current=true;const token=++epoch.current;setLoading(true);setError('');
    try{
      const value=await api('/api/v1/inventory?resource_type=remote-service&limit=100'+(next?'&cursor='+encodeURIComponent(next):''));
      const page=requireObservedInventoryContinuation('services',value,next,100);
      if(token!==epoch.current)return;
      setRows(previous=>next?[...previous,...page.items.filter((item:Row)=>!previous.some(row=>row.id===item.id))]:page.items);
      setCursor(page.next_cursor);setReady(true);
    }catch{if(token===epoch.current)setError('Services could not be read. No empty result was confirmed.')}
    finally{if(token===epoch.current){pending.current=false;setLoading(false)}}
  }
  useEffect(()=>{read();return()=>{epoch.current+=1}},[server.id]);
  const related=rows.filter(row=>row.managed_host_id===server.id);
  return <section className="dr-server-related" aria-label="Services on selected server">
    <h3>Published services</h3>
    {error&&<p className="error" role="alert">{error}</p>}
    {related.map(row=><button key={row.id} type="button" className="dr-server-related-item" onClick={()=>onNavigate?.('services','connections',{inspectResourceId:row.id})}>
      <ServerGlyph kind="service"/><span><strong>{serviceVisibleIdentity(row).primary}</strong><small>{serviceStateLabel(row)} · Open service details</small></span><span aria-hidden="true">→</span>
    </button>)}
    {loading&&<p role="status">Reading services…</p>}
    {ready&&!loading&&!error&&!related.length&&<p>{cursor?'No related services in the pages loaded so far.':'No services reference this server in the returned inventory.'}</p>}
    <div className="dr-wf-actions">{cursor&&<button type="button" className="secondary" disabled={loading} onClick={()=>read(cursor)}>Load more services</button>}{error&&<button className="secondary" type="button" onClick={()=>read()}>Retry</button>}</div>
  </section>;
}

function ServerDetail({server,operator,api,onNavigate,onClose,renderManagement,onTabChange,canManage=true,initialTab='overview',initialAction=null}:{
  server:Row,operator:Actor,api:Props['api'],onNavigate?:Navigate,onClose:()=>void,
  renderManagement?:Props['renderManagement'],onTabChange?:(tab:string)=>void,canManage?:boolean,initialTab?:string,initialAction?:ServerManagementAction|null
}){
  const [tab,setTab]=useState(initialTab),[action,setAction]=useState<ServerManagementAction|null>(initialAction);
  const sheet=useRef<HTMLElement>(null);
  const canEdit=canManage&&knownActor(operator)&&['Admin','Operator'].includes(operator?.role||'');
  const canAdmin=canManage&&knownActor(operator)&&operator?.role==='Admin';
  useEffect(()=>{
    const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
    const node=sheet.current;node?.focus();
    const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
    function keyboard(event:KeyboardEvent){
      if(event.key==="Escape"){event.preventDefault();onClose();return}
      if(event.key==="Tab"&&node){
        const focusable=Array.from(node.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]')).filter(item=>item.getClientRects().length>0);
        if(!focusable.length){event.preventDefault();node.focus();return}
        const first=focusable[0],last=focusable[focusable.length-1];
        if(event.shiftKey&&(document.activeElement===first||document.activeElement===node)){event.preventDefault();last.focus()}
        else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===node)){event.preventDefault();first.focus()}
      }
    }
    document.addEventListener('keydown',keyboard);
    return()=>{document.removeEventListener('keydown',keyboard);document.body.style.overflow=overflow;if(previous?.isConnected)previous?.focus({preventScroll:true})};
  },[]);
  const identity=hostVisibleIdentity(server),facts=hostInventoryFacts(server),next=serverNextAction(server,operator);
  function go(route:string,group:string){onNavigate?.(route,group,{originType:'managed-host',originId:server.id,plane:'remote',serverDetailTab:tab})}
  function changeTab(value:string){setTab(value);setAction(null);onTabChange?.(value)}
  return <div className="dr-server-sheet-backdrop" onMouseDown={event=>{if(event.currentTarget===event.target)onClose()}}>
    <aside ref={sheet} className="dr-server-sheet" role="dialog" aria-modal="true" aria-label="Server details" tabIndex={-1}>
      <header><span className="dr-wf-node-icon"><ServerGlyph/></span><div><p className="dr-eyebrow">Server</p><h2>{identity.primary}</h2><p>{identity.secondary}</p></div><button type="button" className="dr-icon-button" aria-label="Close server details" onClick={onClose}>×</button></header>
      <div className="dr-server-sheet-status"><span className={'dr-wf-state '+(hostConnectionState(server)==='Connected'?'success':'neutral')}>{observedLabel(hostConnectionState(server))}</span><span className={'dr-wf-state '+(server.admission_state==='PENDING_APPROVAL'?'warning':'neutral')}>{approvalLabel(server)}</span></div>
      <div className="dr-server-tabs" role="tablist" aria-label="Server detail sections">{['overview','services','activity','settings'].map(item=><button id={'server-tab-'+item} type="button" key={item} role="tab" aria-selected={tab===item} tabIndex={tab===item?0:-1} onKeyDown={event=>{const tabs=['overview','services','activity','settings'];const index=tabs.indexOf(item);const next=event.key==='ArrowRight'?(index+1)%4:event.key==='ArrowLeft'?(index+3)%4:event.key==='Home'?0:event.key==='End'?3:-1;if(next>=0){event.preventDefault();changeTab(tabs[next]);document.getElementById('server-tab-'+tabs[next])?.focus()}}} aria-controls="server-detail-panel" onClick={()=>changeTab(item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</div>
      <div className="dr-server-sheet-body" id="server-detail-panel" role="tabpanel" aria-labelledby={'server-tab-'+tab}>
        {tab==='overview'&&<>
          <section className="dr-server-next"><ServerGlyph kind={next==='approval'?'shield':'service'}/><div><h3>{next==='approval'?'Ready for your review':next==='diagnose'?'Check the Agent connection':next==='services'?'Choose a service to use':'Review this server'}</h3><p>{next==='approval'?'Verify this server before approving access.':next==='diagnose'?'The current report does not confirm an Agent connection.':next==='services'?'Agent status and service access are separate checks.':'Approval, management trust and connectivity are separate.'}</p>
            {next==='approval'&&canAdmin&&<button type="button" className="primary" onClick={()=>{setTab('settings');setAction('admission');onTabChange?.('settings')}}>Review approval</button>}
            {next==='diagnose'&&<button type="button" className="primary" onClick={()=>go('access','access')}>Diagnose connection</button>}
            {next==='services'&&<button type="button" className="primary" onClick={()=>changeTab('services')}>View services</button>}
          </div></section>
          <dl className="dr-server-summary"><div><dt>Platform</dt><dd>{observedLabel(facts.platform)}</dd></div><div><dt>Agent version</dt><dd>{observedLabel(facts.version)}</dd></div><div><dt>Management trust</dt><dd>{observedLabel(facts.trust)}</dd></div><div><dt>Agent heartbeat</dt><dd>{observedLabel(facts.lastHeartbeat)}</dd></div></dl>
          <details className="dr-wf-disclosure"><summary>Technical details</summary>{hostDetailSections(server).map(section=><section key={section.title}><h3>{section.title}</h3><dl className="dr-server-summary">{section.fields.map(field=><div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl></section>)}<p>Reported Agent heartbeat is not a service reachability test. Last activity is the separate Core timestamp.</p></details>
        </>}
        {tab==='services'&&<RelatedServerServices key={server.id} server={server} api={api} onNavigate={(id,group,context)=>onNavigate?.(id,group,{...context,serverDetailTab:tab})}/>}
        {tab==='activity'&&<section className="dr-server-next"><ServerGlyph kind="search"/><div><h3>Activity for this server</h3><p>Open the activity log with this server selected.</p><button type="button" className="primary" onClick={()=>go('audit','activity')}>Open activity log</button></div></section>}
        {tab==='settings'&&<>
          <h3>Settings for {identity.primary}</h3><p className="dr-wf-caption">Changes below stay bound to this selected server.</p>
          {!canEdit&&<p className="dr-wf-readonly">Read only. Ask an Admin to change this server.</p>}
          {!action&&<div className="dr-server-settings-actions">
            {canEdit&&<button type="button" className="secondary" onClick={()=>setAction('metadata')}>Edit name, description and tags <span aria-hidden="true">→</span></button>}
            {canAdmin&&<button type="button" className="secondary" onClick={()=>setAction('admission')}>Review approval or quarantine <span aria-hidden="true">→</span></button>}
            {canAdmin&&<details className="dr-wf-disclosure"><summary>Advanced lifecycle actions</summary><p>Revocation and retirement retain their existing impact review and confirmation.</p><button type="button" className="secondary" onClick={()=>setAction('lifecycle')}>Review lifecycle action</button></details>}
          </div>}
          {action&&canEdit&&(action==='metadata'||canAdmin)&&<div className="dr-server-management"><button className="dr-text-action" type="button" onClick={()=>setAction(null)}>← Back to server settings</button>{renderManagement?.(server,action)}</div>}
        </>}
      </div>
      <footer><span className="dr-wf-caption">Server state is reported, not a live access verdict.</span><button type="button" className="secondary" onClick={onClose}>Done</button></footer>
    </aside>
  </div>;
}

export function ServerWorkspace({data,operator,api,onNavigate,onRefresh,initialFilter='',initialAdmission='all',initialInspectId,renderManagement,readState='ready',initialView,onReturnStateChange}:Props){
  const validated=useMemo(()=>observedPage(data),[data]);
  const actorKey=(operator?.id||'')+':'+(operator?.role||'');
  const [inventory,setInventory]=useState(()=>({base:data,actor:actorKey,rows:validated?.items||[],cursor:validated?.next_cursor||null,pages:1}));
  const current=inventory.base===data&&inventory.actor===actorKey?inventory:{base:data,actor:actorKey,rows:validated?.items||[],cursor:validated?.next_cursor||null,pages:1};
  const [filter,setFilter]=useState(initialFilter),[admission,setAdmission]=useState<HostAdmission>(isSavedAdmission(initialAdmission)?initialAdmission:'all');
  const [connection,setConnection]=useState<HostConnectionFilter>(initialView?.connection||'all'),[sort,setSort]=useState<HostSortMode>(initialView?.sort||'review');
  const [reviewOnly,setReviewOnly]=useState(initialView?.reviewOnly||false),[cards,setCards]=useState(initialView?.cards||false);
  const [busy,setBusy]=useState(false),[moreError,setMoreError]=useState('');
  const [selection,setSelection]=useState(()=>({id:validId(initialInspectId)?initialInspectId:'',base:data,actor:actorKey,tab:initialView?.detailTab||'overview',action:null as ServerManagementAction|null}));
  const epoch=useRef(0),pending=useRef(false),previousInspect=useRef(initialInspectId);
  useEffect(()=>{
    const navigationChanged=previousInspect.current!==initialInspectId;previousInspect.current=initialInspectId;
    epoch.current+=1;pending.current=false;setBusy(false);setMoreError('');
    setInventory({base:data,actor:actorKey,rows:validated?.items||[],cursor:validated?.next_cursor||null,pages:1});
    setSelection(previous=>({id:previous.actor===actorKey&&!navigationChanged?previous.id:validId(initialInspectId)?initialInspectId:'',base:data,actor:actorKey,tab:previous.actor===actorKey&&!navigationChanged?previous.tab:'overview',action:null}));
    return()=>{epoch.current+=1};
  },[data,actorKey,initialInspectId]);
  useEffect(()=>{if(readState!=='ready'){epoch.current+=1;pending.current=false;setBusy(false);setSelection(previous=>({...previous,action:null}))}},[readState]);
  useEffect(()=>{setFilter(initialFilter);setAdmission(isSavedAdmission(initialAdmission)?initialAdmission:'all');
    setConnection(initialView?.connection||'all');setSort(initialView?.sort||'review');setCards(initialView?.cards||false);setReviewOnly(initialView?.reviewOnly||false)
  },[initialFilter,initialAdmission,initialView]);
  useEffect(()=>{if(initialView){const frame=requestAnimationFrame(()=>window.scrollTo(0,initialView.scrollTop));return()=>cancelAnimationFrame(frame)}},[]);
  function remember(detailTab=selection.tab){
    if(knownActor(operator))onReturnStateChange?.({actor:actorKey,filter,admission,connection,sort,cards,reviewOnly,
      inspectResourceId:selection.id,detailTab,
      scrollTop:Math.max(0,Math.min(10000000,Math.round(window.scrollY)))});
  }
  // Capture display choices even when navigation originates in the sidebar.
  // The shell stores them in a ref, not a live input fed back into this view.
  useEffect(()=>{
    remember();let frame=0;
    const scroll=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>remember())};
    window.addEventListener('scroll',scroll,{passive:true});
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('scroll',scroll)};
  },[actorKey,filter,admission,connection,sort,cards,reviewOnly,selection.id,selection.tab,onReturnStateChange]);
  function navigate(id:string,group?:string,context?:any){
    remember(['overview','services','activity','settings'].includes(context?.serverDetailTab)?context.serverDetailTab:selection.tab);
    onNavigate?.(id,group,context);
  }
  const selected=selection.base===data&&selection.actor===actorKey&&knownActor(operator)
    ?current.rows.filter((row:Row)=>row.id===selection.id):[];
  function inspect(row:Row,review=false){
    if(!knownActor(operator)||!validId(row.id))return;
    setSelection({id:row.id,base:data,actor:actorKey,tab:review?'settings':'overview',action:review?'admission':null});
  }
  function close(){setSelection(previous=>({...previous,id:''}))}
  async function loadMore(){
    const cursor=current.cursor;if(!cursor||pending.current||!knownActor(operator)||readState!=='ready')return;
    const token=++epoch.current;pending.current=true;setBusy(true);setMoreError('');
    try{
      const raw=await api('/api/v1/inventory?resource_type=managed-host&limit=100&cursor='+encodeURIComponent(cursor));
      const next=requireObservedInventoryContinuation('hosts',raw,cursor,100);
      if(token!==epoch.current)return;
      const fresh=next.items.filter((row:Row)=>!current.rows.some((old:Row)=>old.id===row.id));
      if(next.items.length&&!fresh.length)throw new Error('Repeated inventory page');
      setInventory({...current,rows:[...current.rows,...fresh],cursor:next.next_cursor,pages:current.pages+1});
    }catch{if(token===epoch.current)setMoreError('The next page could not be verified. Existing servers are unchanged.')}
    finally{if(token===epoch.current){pending.current=false;setBusy(false)}}
  }
  function clearFilters(){setFilter('');setAdmission('all');setConnection('all');setSort('review');setReviewOnly(false)}
  function removeChip(id:HostFilterChipId){if(id==='search')setFilter('');else if(id==='admission')setAdmission('all');else if(id==='connection')setConnection('all');else if(id==='sort')setSort('review')}
  if(!validated)return <section className="card dr-workflow-servers" role="alert"><h2>Server inventory unavailable</h2><p>No empty or healthy result was confirmed.</p><button className="secondary" type="button" onClick={onRefresh}>Retry</button></section>;
  const canAdd=readState==='ready'&&knownActor(operator)&&operator?.role==='Admin';
  if(!current.rows.length&&!current.cursor&&readState==='ready'&&!filter&&admission==='all'&&connection==='all'&&!reviewOnly)return <section className="dr-workflow-servers dr-server-welcome" aria-label="First server setup">
    <span className="dr-wf-kicker">START WITH ONE CONNECTION</span>
    <RemoteConnectionDiagram/>
    <h2>Connect your first server</h2>
    <p>Install an Agent, review the server, then publish only the services you need.</p>
    {canAdd?<div className="dr-server-welcome-actions"><button type="button" className="primary" onClick={()=>navigate('enrollments','connections')}>Add server</button><button type="button" className="dr-text-action" onClick={()=>navigate('enrollments','connections')}>Already installed an Agent? →</button></div>:<p className="dr-wf-readonly">Ask an Admin to add the first server.</p>}
    <ol className="dr-server-setup-steps"><li><span>1</span><div><strong>Install Agent</strong><small>Copy the command for your platform</small></div></li><li><span>2</span><div><strong>Review server</strong><small>Check identity before approval</small></div></li><li><span>3</span><div><strong>Publish a service</strong><small>Choose what may be accessed</small></div></li></ol>
  </section>;
  const search=filterObservedHosts(current.rows,filter,admission);
  const connectionRows=filterLoadedHostConnections(search.items,connection);
  const rows=sortLoadedHosts(reviewOnly?connectionRows.items.filter(row=>hostConnectionState(row)!=='Connected'):connectionRows.items,sort);
  const chips=activeHostFilterChips(filter,admission,connection,sort);
  const filtered=!!filter||admission!=='all'||connection!=='all'||reviewOnly;
  const draft=!search.error?saveDraftForResource('host',filter,admission):null;
  const pendingCount=current.rows.filter((row:Row)=>row.admission_state==='PENDING_APPROVAL').length;
  const reviewCount=current.rows.filter((row:Row)=>hostConnectionState(row)!=='Connected').length;
  return <div className="dr-workflow-servers" data-read-state={readState}>
    <div className="dr-wf-toolbar"><p>{current.rows.length} loaded servers <span className="dr-wf-caption">· {current.cursor?'More pages available':'End of returned inventory'}</span></p><div className="dr-wf-actions"><button type="button" className="secondary" onClick={onRefresh}>Refresh</button>{canAdd&&<button type="button" className="primary" onClick={()=>navigate('enrollments','connections')}>Add server</button>}</div></div>
    <section className="dr-server-inventory">
      <div className="dr-server-status-tabs" role="group" aria-label="Server status filters">
        <button type="button" aria-pressed={admission==='all'&&!reviewOnly} onClick={()=>{setAdmission('all');setReviewOnly(false)}}>All servers <span>{current.rows.length}</span></button>
        <button type="button" aria-pressed={admission==='PENDING_APPROVAL'&&!reviewOnly} onClick={()=>{setAdmission('PENDING_APPROVAL');setReviewOnly(false)}}>Pending approval <span className={pendingCount?'warning':''}>{pendingCount}</span></button>
        <button type="button" aria-pressed={reviewOnly} onClick={()=>{setAdmission('all');setReviewOnly(true)}}>Connection needs review <span>{reviewCount}</span></button>
      </div>
      <div className="dr-server-list-tools"><label className="dr-server-search"><ServerGlyph kind="search"/><input maxLength={120} aria-label="Search servers" placeholder="Search servers…" value={filter} onChange={event=>setFilter(event.target.value)}/>{filter&&<button type="button" aria-label="Clear search" onClick={()=>setFilter('')}>×</button>}</label>
        <details className="dr-server-filter-menu"><summary><ServerGlyph kind="filter"/>Filters</summary><div className="dr-server-filter-body">
          <label>Approval<select aria-label="Approval filter" value={admission} onChange={event=>setAdmission(isSavedAdmission(event.target.value)?event.target.value:'all')}><option value="all">All approval states</option><option value="PENDING_APPROVAL">Pending approval</option><option value="APPROVED">Approved</option><option value="QUARANTINED">Quarantined</option></select></label>
          <label>Agent connection<select aria-label="Agent connection filter" value={connection} onChange={event=>setConnection(event.target.value as HostConnectionFilter)}><option value="all">All connections</option><option value="connected">Connected</option><option value="disconnected">Disconnected</option><option value="unknown">Not reported</option></select></label>
          <label>Sort<select aria-label="Server sort" value={sort} onChange={event=>setSort(isHostSortMode(event.target.value)?event.target.value:'review')}><option value="review">Review priority</option><option value="name_asc">Name A–Z</option><option value="name_desc">Name Z–A</option></select></label>
          <button type="button" className="secondary" aria-pressed={cards} onClick={()=>setCards(!cards)}>{cards?'Use table view':'Use cards view'}</button>
          <button type="button" className="dr-text-action" onClick={clearFilters}>Reset filters</button>
        </div></details>
        {draft&&<button type="button" className="secondary" onClick={()=>navigate('views','activity',{savedViewDraft:draft})}>Save view</button>}
      </div>
      {(chips.length>0||reviewOnly)&&<div className="dr-wf-filter-chips" aria-label="Active server filters">{chips.map(chip=><button key={chip.id} type="button" onClick={()=>removeChip(chip.id)} aria-label={'Remove '+chip.label+' filter'}>{chip.label}: {chip.value} ×</button>)}{reviewOnly&&<button type="button" onClick={()=>setReviewOnly(false)}>Connection review ×</button>}<button type="button" onClick={clearFilters}>Clear filters</button></div>}
      {search.error&&<p className="error" role="alert">Search not applied: {search.error}</p>}
      {(search.warning||connectionRows.unknownCount>0)&&<p className="dr-wf-inline-note" role="status">Some server facts are not reported. Filters cover loaded records only.</p>}
      {!rows.length?<div className="dr-server-no-match"><ServerGlyph kind="search"/><h3>No matching servers</h3><p>{current.cursor?'More servers may exist on pages not yet loaded.':'Try another filter or review unreported server states.'}</p>{filtered&&<button type="button" className="secondary" onClick={clearFilters}>Clear filters</button>}</div>:
        cards?<div className="dr-server-card-grid" role="list">{rows.map(row=>{const card=resourceCardSummary('host',row);return card?<button type="button" key={row.id} className="dr-server-item-card" onClick={()=>inspect(row)}><ServerGlyph/><strong>{card.title}</strong><span className="dr-wf-caption">{card.subtitle}</span><span className={'dr-wf-state '+(card.status==='Connected'?'success':'neutral')}>{observedLabel(card.status)}</span><span>{approvalLabel(row)}</span><span className="dr-text-action">View server →</span></button>:null})}</div>:
        <div className="dr-server-table-scroll"><table className="dr-server-table"><thead><tr><th scope="col">Server</th><th scope="col">Agent connection</th><th scope="col">Approval</th><th scope="col">Services</th><th scope="col">Last observed</th><th scope="col">Action</th></tr></thead><tbody>{rows.map(row=>{const facts=hostInventoryFacts(row),identity=hostVisibleIdentity(row),next=serverNextAction(row,operator);return <tr key={row.id}>
          <td data-label="Server"><button type="button" className="dr-server-name" onClick={()=>inspect(row)}><span className="dr-server-platform"><ServerGlyph/></span><span><strong>{identity.primary}</strong><small>{observedLabel(facts.platform)} · {identity.secondary}</small></span></button></td>
          <td data-label="Agent connection"><span className={'dr-wf-state '+(hostConnectionState(row)==='Connected'?'success':hostConnectionState(row)==='Disconnected'?'warning':'neutral')}>{observedLabel(hostConnectionState(row))}</span></td>
          <td data-label="Approval"><span className={'dr-wf-state '+(row.admission_state==='PENDING_APPROVAL'?'warning':'neutral')}>{approvalLabel(row)}</span></td>
          <td data-label="Services">Not reported</td><td data-label="Last observed"><span>{observedLabel(facts.lastHeartbeat)}</span><small className="dr-server-observed-kind">Agent heartbeat</small></td>
          <td data-label="Action"><button type="button" className={next==='approval'?'dr-server-review':'dr-text-action'} onClick={()=>{if(next==='diagnose')navigate('access','access',{originType:'managed-host',originId:row.id,plane:'remote'});else if(next==='services')setSelection({id:row.id,base:data,actor:actorKey,tab:'services',action:null});else inspect(row,next==='approval')}}>{next==='approval'?'Review approval':next==='diagnose'?'Diagnose':next==='services'?'View services':'Details'} →</button></td>
        </tr>})}</tbody></table></div>}
      <div className="dr-server-list-footer"><span>{rows.length} shown · {current.rows.length} loaded · {current.pages} page{current.pages===1?'':'s'}</span>{current.cursor&&<button type="button" className="secondary" disabled={busy} onClick={loadMore}>{busy?'Loading…':'Load more'}</button>}</div>
      {moreError&&<p role="alert" className="error">{moreError}</p>}
    </section>
    <details className="dr-wf-disclosure"><summary>Technical details</summary><p>Filters and counts cover the pages loaded above, not a separate total. Use name:, host:, os:, admission: or id: for advanced search. Saved views retain search and approval selection, not connection filters or sorting.</p><p>Agent connection, approval and management trust are distinct. Agent heartbeat and Core last activity are separate timestamps. A reported connection does not prove a service is reachable.</p></details>
    {selected.length===1&&<ServerDetail key={actorKey+':'+selected[0].id} server={selected[0]} operator={operator} api={api} onNavigate={navigate} onClose={close} onTabChange={tab=>setSelection(previous=>({...previous,tab}))} renderManagement={renderManagement} canManage={readState==='ready'} initialTab={selection.tab} initialAction={selection.action}/>}
  </div>;
}


/** Production Servers route. The caller keys this component by authenticated actor.
 * Retained rows on failed refresh are explicitly stale, read-only evidence; never first use.
 * No actor, filter or response is persisted here and no by-ID authority is introduced.
 */
export function ServerRoute({operator,api,onNavigate,context,renderManagement,returnState,onReturnStateChange}:{
  operator:Actor,api:Props['api'],onNavigate?:Navigate,context?:any,renderManagement?:Props['renderManagement'],returnState?:unknown,onReturnStateChange?:Props['onReturnStateChange']
}){
  const restored=useMemo(()=>{
    const saved=observedServerReturnState(returnState,operator);
    if(!saved)return null;
    const explicit=context?.savedFilter!==undefined||context?.savedAdmission!==undefined||context?.inspectResourceId!==undefined;
    return !explicit||!context?.searchResultKey&&context?.inspectResourceId===saved.inspectResourceId?saved:null;
  },[returnState,operator?.id,operator?.role,context]);
  const [data,setData]=useState<unknown>(null),[status,setStatus]=useState<'loading'|'ready'|'refreshing'|'unavailable'|'stale'>('loading');
  const [error,setError]=useState('');
  const currentData=useRef<unknown>(null),epoch=useRef(0),controller=useRef<AbortController|null>(null);
  async function read(){
    const token=++epoch.current;controller.current?.abort();
    const abort=new AbortController();controller.current=abort;
    setStatus(currentData.current?'refreshing':'loading');setError('');
    const timer=setTimeout(()=>abort.abort(),15000);
    try{
      const value=await api('/api/v1/inventory?resource_type=managed-host&limit=100',{signal:abort.signal});
      if(token!==epoch.current)return;
      const page=observedPage(value);
      if(!page)throw new Error('The returned server inventory is incomplete or inconsistent.');
      currentData.current=page;setData(page);setStatus('ready');
    }catch{
      if(token!==epoch.current)return;
      setStatus(currentData.current?'stale':'unavailable');
      setError(abort.signal.aborted?'The server inventory request timed out.':'Server inventory could not be verified.');
    }finally{clearTimeout(timer)}
  }
  useEffect(()=>{read();return()=>{epoch.current+=1;controller.current?.abort()}},[]);
  if(status==='loading')return <section className="dr-workflow-servers dr-server-loading" aria-busy="true"><p role="status">Reading servers…</p><div className="dr-server-loading-rows" aria-hidden="true"><span/><span/><span/></div></section>;
  if(status==='unavailable')return <section className="card dr-workflow-servers" role="alert"><h2>Server inventory unavailable</h2><p>{error} No empty result was confirmed.</p><button type="button" className="secondary" onClick={read}>Retry</button></section>;
  return <>
    {status==='refreshing'&&<p className="dr-wf-inline-note" role="status">Refreshing servers… Previous observations are read only.</p>}
    {status==='stale'&&<section className="warning-box" role="alert"><strong>Previous server observations · not current</strong><p>{error} Refresh successfully before making changes.</p><button type="button" className="secondary" onClick={read}>Retry</button></section>}
    <ServerWorkspace data={data} operator={operator} api={api} onNavigate={onNavigate} onRefresh={read}
      readState={status==='refreshing'?'refreshing':status==='stale'?'stale':'ready'}
      initialFilter={restored?.filter??String(context?.savedFilter||'').slice(0,120)} initialAdmission={restored?.admission??context?.savedAdmission}
      initialInspectId={restored?.inspectResourceId??context?.inspectResourceId} initialView={restored} onReturnStateChange={onReturnStateChange} renderManagement={renderManagement}/>
  </>;
}
