import React,{useEffect,useRef,useState} from "react";
import {EnrollmentOnboarding,hostReadinessLabel} from "./p0-enrollment";
import {AccessEvidenceExplorer,GuidedPolicyJourney,type AccessPlane,type LinkApi} from "./p0-access-policy";
import {RemoteServiceEditor} from "./uxb-remote-service";
import {CoreChoiceField,type CoreCatalog} from "./uxb-core-choices";
type Navigate=(id:string,groupId?:string,context?:any)=>void;
export type SetupDraft={
  plane?:AccessPlane,step?:number,selectedHost?:string,serviceName?:string,
  source?:string,destination?:string,selector?:string,
  service?:{owner:string,name:string,service:string,destination:string}
};

export const connectionTypes=[
  {id:"remote",title:"Connect to an internal server",detail:"Remote Access · Open only the selected service, such as SSH, to authorized users outside.",example:"Example: administrator → SSH on one server"},
  {id:"internet",title:"Let a server reach the Internet",detail:"Internet Access · Allow an internal source to reach only approved outside destinations.",example:"Example: update server → approved update site"},
  {id:"ai",title:"Allow an AI integration",detail:"AI Access · Grant a verified AI Identity only an explicitly named permission.",example:"Example: automation bot → read-only status"},
] as const;

export const firstUseStages = {
  remote:["Add & approve Agent","Publish one Remote Service","Define a narrow access rule","Verify the decision"],
  internet:["Select managed source","Choose outside destination","Define an Internet Access rule","Verify the decision"],
  ai:["Select AI Identity","Choose a Permission Object","Define an AI Access rule","Verify the permission"],
} as const;

/** Only a deliberate owner change resets a resumed, non-secret first-use draft.
 * It does not touch the Core: old preview/confirmation belongs to the editor. */
export function retargetRemoteHost(draft:SetupDraft,hostId:string):SetupDraft{
  const next=hostId.trim();
  return {...draft,selectedHost:next,serviceName:"",source:"",destination:"",selector:"",
    service:{owner:next,name:"",service:"",destination:"this-host"}};
}

/** A resumed, non-secret draft may predate explicit Host-selection semantics.
 * Never make the displayed Agent own a service draft originally prepared for another Host. */
export function reconcileHostBoundDraft(draft?:SetupDraft|null):SetupDraft{
  if(!draft)return {};
  if((draft.plane||"remote")!=="remote")return draft;
  const selectedHost=String(draft.selectedHost||"").trim();
  const storedOwner=String(draft.service?.owner||"").trim();
  if(storedOwner&&storedOwner!==selectedHost)
    return retargetRemoteHost(draft,selectedHost);
  return draft;
}

export function firstConnectionGuidance(
  plane:AccessPlane,step:number,state:{
    hosts:any[]|null,selectedHost:string,source:string,destination:string,
    selector:string,serviceName:string,
  }
):string{
  if(step===4)return "NOT VERIFIED · Run an actual Core decision trace, then verify client and Agent reachability separately.";
  if(plane==="remote"){
    if(step===1){
      if(state.hosts===null)return "Agent inventory UNKNOWN · Refresh Core inventory before deciding which Agent to use.";
      if(!state.selectedHost)return "Add an Agent or Select an observed Agent below. Admission, trust and connection are separate checks.";
      const host=state.hosts.find(item=>String(item.id)===state.selectedHost);
      if(!host)return "Selected Agent not observed in current Core inventory. Refresh and choose the intended Host.";
      if(host.admission_state!=="APPROVED")return "The selected Agent still needs Admin approval. Publishing does not bypass admission.";
      if(String(host.trust_status||"").toLowerCase()!=="trusted")return "The selected Agent's trust is not verified. Review Host trust before continuing.";
      if(host.connected!==true&&host.connected!==1)return "The selected Agent is not observed connected. Check Agent connectivity.";
      return "Agent selected · approval, trust and connection observed. Now publish one service; access remains NOT VERIFIED.";
    }
    if(step===2){
      if(!state.selectedHost)return "Select the intended Agent before previewing a Remote Service.";
      if(!state.serviceName.trim())return "Name and preview one service for this Agent. Confirm only the reviewed Core job.";
      return "Service name entered · inspect the actual Agent job and published inventory; target connectivity is NOT VERIFIED.";
    }
  }else if(step===1){
    if(!state.source.trim())return plane==="ai"
      ?"Choose an existing AI Identity. An identity must be configured and verified before granting permission."
      :"Choose the managed source Network Object or Group before defining Internet Access.";
    return "Source name selected · check its Core identity and proceed. No access has been granted.";
  }else if(step===2){
    if(!state.destination.trim()||!state.selector.trim())return plane==="ai"
      ?"Choose a permission and destination for this AI Identity. Neither is an SSH port."
      :"Choose an outside destination and service for this managed source.";
    return "Destination and selector chosen · they are only form values until Core Preview and required tests pass.";
  }
  if(step===3){
    if(!state.source.trim()||!state.destination.trim()||!state.selector.trim())
      return "Choose the source, destination and "+(plane==="ai"?"permission":"service")+" before requesting a Core policy Preview.";
    return "Review the exact rule in Core Preview, run required regression tests and type the final confirmation; nothing is applied yet.";
  }
  return "Choose your intended task; Core observations determine readiness, not this progress indicator.";
}

export function FirstConnectionSetup({api,operator,onNavigate,initialDraft,onDraftChange}:{
  api:LinkApi,operator:any,onNavigate?:Navigate,initialDraft?:SetupDraft|null,
  onDraftChange?:(draft:SetupDraft)=>void,
}){
  const restoredDraft=reconcileHostBoundDraft(initialDraft);
  const [plane,setPlane]=useState<AccessPlane>(restoredDraft.plane||"remote");
  const [step,setStep]=useState(Math.min(4,Math.max(1,restoredDraft.step||1)));
  const [hosts,setHosts]=useState<any[]|null>(null),[services,setServices]=useState<any[]|null>(null);
  const [catalog,setCatalog]=useState<CoreCatalog|null>(null);
  // Null means not observed / API unavailable; an authoritative empty list is different.
  const [enrollments,setEnrollments]=useState<any>(null);
  const [error,setError]=useState(""),[checking,setChecking]=useState(false);
  const [serviceBusy,setServiceBusy]=useState(false);
  const [enrollmentBusy,setEnrollmentBusy]=useState(false);
  const wizardBusy=serviceBusy||enrollmentBusy;
  const [selectedHost,setSelectedHost]=useState(restoredDraft.selectedHost||"");
  const selectedHostRef=useRef(restoredDraft.selectedHost||"");
  const refreshGeneration=useRef(0);
  const planeRef=useRef(plane);
  const [serviceName,setServiceName]=useState(restoredDraft.serviceName||"");
  const [serviceDraft,setServiceDraft]=useState(restoredDraft.service||{owner:"",name:"",service:"",destination:"this-host"});
  const [source,setSource]=useState(restoredDraft.source||"");
  const [destination,setDestination]=useState(restoredDraft.destination||"");
  const [selector,setSelector]=useState(restoredDraft.selector||"");
  const canEdit=operator?.role==="Admin"||operator?.role==="Operator";
  const selected=hosts?.find(h=>String(h.id)===selectedHost)||null;
  const service=services?.find(s=>String(s.name||s.id)===serviceName)||null;
  function chooseRemoteHost(nextHost:string){
    if(nextHost===selectedHostRef.current)return;
    selectedHostRef.current=nextHost;
    const cleared=retargetRemoteHost({
      plane,step,selectedHost,serviceName,source,destination,selector,service:serviceDraft,
    },nextHost);
    setSelectedHost(cleared.selectedHost||"");
    setServiceDraft(cleared.service!);
    setServiceName("");setSource("");setDestination("");setSelector("");setError("");
  }
  useEffect(()=>{void refreshCore();return()=>{refreshGeneration.current+=1;}},[]);
  // Only non-secret form choices stay in Shell's current authenticated React
  // session. A Core change plan, OTP, token or invitation is never persisted.
  useEffect(()=>{onDraftChange?.({plane,step,selectedHost,serviceName,
    source,destination,selector,service:serviceDraft})},
    [plane,step,selectedHost,serviceName,source,destination,selector,serviceDraft]);
  async function refreshCore(){
    const generation=++refreshGeneration.current;
    setChecking(true);setError("");
    const r=await Promise.allSettled([
      api("/api/v1/inventory?resource_type=managed-host&limit=100"),
      api("/api/v1/inventory?resource_type=remote-service&limit=100"),
      api("/api/v1/enrollments?limit=50"),
      api("/api/v1/objects-groups?limit=50"),
    ]);
    // An older Core snapshot cannot override a newer completed refresh.
    if(refreshGeneration.current!==generation)return;
    if(r[0].status==="fulfilled"&&Array.isArray(r[0].value?.items)){
      const list=r[0].value.items;setHosts(list);
      // Do not silently switch the owning Agent to the first list entry.
      // Also discard the retained editor owner when its formerly selected
      // Agent vanishes; a remounted editor must not revive that old target.
      const currentHost=selectedHostRef.current;
      if(currentHost&&!list.some((x:any)=>String(x.id)===currentHost)){
        // A previously selected Agent is not evidence of another live owner.
        if(planeRef.current==="remote")chooseRemoteHost("");
        else{
          selectedHostRef.current="";
          setSelectedHost("");setServiceDraft(prev=>({...prev,owner:""}));
        }
      }
    }else{setHosts(null);setError("Managed Host inventory unavailable; prerequisite state is UNKNOWN.");
      if(planeRef.current==="remote"&&selectedHostRef.current)chooseRemoteHost("");}
    if(r[1].status==="fulfilled"&&Array.isArray(r[1].value?.items))setServices(r[1].value.items);
    else setServices(null);
    if(r[2].status==="fulfilled"&&Array.isArray(r[2].value?.items))setEnrollments(r[2].value);
    else setEnrollments(null); // UNKNOWN, never a fabricated empty enrollment list.
    if(r[3].status==="fulfilled"&&r[3].value?.resources&&typeof r[3].value.resources==="object")
      setCatalog(r[3].value as CoreCatalog);
    else setCatalog(null); // A failed snapshot cannot be treated as zero objects.
    setChecking(false);
  }
  const stages=firstUseStages[plane];
  const nextAction=firstConnectionGuidance(plane,step,{hosts,selectedHost,source,destination,selector,serviceName});
  function changePlane(value:AccessPlane){
    if(value===planeRef.current)return;
    planeRef.current=value;selectedHostRef.current="";
    setPlane(value);setSelectedHost("");setStep(1);setSource("");setDestination("");setSelector("");
    setServiceName("");setServiceDraft({owner:"",name:"",service:"",destination:"this-host"});setError("");
  }
  return <div className="dr-uxb-setup" data-testid="uxb-connection-setup">
    <section className="card dr-uxb-setup-hero">
      <p className="dr-eyebrow">One safe path · Core-authoritative connection setup</p>
      <h2>Set up and verify a connection</h2>
      <p className="muted">One workspace, four stages. Progress indicates where you are, not that Core has completed a step. Every change still requires its own preview, tests and confirmation.</p>
      <div className="dr-uxb-mode-select" role="group" aria-label="What are you connecting?">
        <strong>1. What would you like to connect?</strong>
        <div className="dr-uxb-mode-grid">{connectionTypes.map(item=><button key={item.id} type="button"
          className={plane===item.id?"dr-uxb-mode-card active":"dr-uxb-mode-card"}
          aria-pressed={plane===item.id} disabled={wizardBusy} onClick={()=>changePlane(item.id)}>
          <strong>{item.title}</strong><span>{item.detail}</span><small>{item.example}</small>
        </button>)}</div>
      </div>
      <div className="dr-uxb-setup-summary" role="status">Current stage {step} of 4 · {firstUseStages[plane][step-1]}. Changing stages does not modify access.</div>
      <ol className="dr-uxb-stage-menu" aria-label="First-connection stages">
        {stages.map((title,i)=><li key={title} className={step===i+1?"active":""}>
          <button type="button" aria-current={step===i+1?"step":undefined} disabled={wizardBusy} onClick={()=>setStep(i+1)}>
            <span>{i+1}</span><strong>{title}</strong></button>
        </li>)}
      </ol>
      <div className="dr-uxb-flow-buttons">
        <button className="secondary" disabled={step===1||wizardBusy} onClick={()=>setStep(i=>Math.max(1,i-1))}>← Previous</button>
        <button className="primary" disabled={step===4||wizardBusy} onClick={()=>setStep(i=>Math.min(4,i+1))}>{step===4?"Review Core decision below":"Next: "+stages[step]+" →"}</button>
        <button className="secondary" onClick={refreshCore} disabled={checking||wizardBusy}>{checking?"Checking Core…":"Refresh observed state"}</button>
      </div>
      <div className="dr-uxb-next-guidance" role="status" aria-live="polite"><strong>What to do next</strong><p>{nextAction}</p>
        <small>Stage navigation is for reviewing tasks, not evidence of completion. Core confirmation remains required.</small>
      </div>
      {wizardBusy&&<p className="dr-uxb-busy-note" role="status">Core operation in progress · Finish and review its result before switching Agent or setup stages.</p>}
      <details className="dr-uxb-glossary"><summary>What do Agent, Remote Service and Access Rule mean?</summary>
        <dl><dt>Agent / Managed Host</dt><dd>A protected server running Data Relay Link Agent. Connected alone is not approved or trusted.</dd>
          <dt>Remote Service</dt><dd>One explicitly published internal application or port, such as SSH, not a whole network.</dd>
          <dt>Access Rule</dt><dd>Who may reach a named destination through a Service Object or named AI permission. Core enforces it.</dd>
          <dt>Verified</dt><dd>A saved rule or queued job is not a working connection. Check the Core decision and actual client/Agent evidence separately.</dd></dl>
      </details>
      {error&&<p className="warning-box" role="alert">{error}</p>}
      {plane==="remote"&&<div className="dr-uxb-evidence-strip">
        <span>Agent: {selected?hostReadinessLabel(selected):hosts===null?"UNKNOWN":"NO HOST SELECTED"}</span>
        <span>Remote Service: {service?String(service.enabled?"CONFIGURED · VERIFY JOB":"DISABLED · VERIFY JOB"):services===null?"UNKNOWN":"NOT SELECTED"}</span>
        <span>Core policy reachability: NOT VERIFIED</span>
      </div>}
    </section>
    {step===1&&plane==="remote"&&<>
      <div className="dr-uxb-context">
        <strong>Why add an Agent?</strong>
        <p>A Managed Host is the internal server running a DRLink Agent. Installing one does not publish its ports or grant all users access.</p>
      </div>
      <EnrollmentOnboarding api={api} data={enrollments} refresh={refreshCore} operator={operator} onNavigate={onNavigate}
        onBusyChange={setEnrollmentBusy}/>
      <section className="card dr-uxb-choice"><h3>Continue with an enrolled server</h3>
        <label className="dr-field"><span>Managed Host</span><select value={selectedHost} disabled={wizardBusy} onChange={e=>chooseRemoteHost(e.target.value)}>
          {!selectedHost&&<option value="">{hosts===null?"Managed Host inventory: UNKNOWN":hosts.length?"Select an observed Managed Host":"No observed Managed Host"}</option>}
          {(hosts||[]).map(h=><option key={h.id} value={String(h.id)}>{h.name||h.label||h.id} · {h.id}</option>)}
        </select></label>
        {selected&&<p>{hostReadinessLabel(selected)} · Trust: {selected.trust_status||"UNKNOWN"} · Last seen: {selected.agent_heartbeat_at||"UNKNOWN"}</p>}
        <p className="muted">An unobserved, disconnected or pending-approval Host is not ready for a verified connection.</p>
      </section>
    </>}
    {step===1&&plane!=="remote"&&<section className="card dr-uxb-choice">
      <h3>{plane==="internet"?"Identify the managed source":"Select a trusted AI Identity"}</h3>
      <p>{plane==="internet"
        ?"Internet Access controls permitted outbound requests from a managed/protected source, not published inbound Remote Services."
        :"AI Access grants named permissions to an authenticated AI Identity. It does not expose an SSH port."}</p>
      <CoreChoiceField api={api} catalog={catalog} plane={plane} field="source" value={source} onChoose={setSource}/>
      {source&&<p className="dr-uxb-selection-note">Selected source: <strong>{source}</strong>. Core checks its meaning during policy preview.</p>}
      <button className="secondary" onClick={()=>onNavigate?.("objects","access",{family:plane==="ai"?"ai":"network"})}>{plane==="internet"?"Browse Network Objects & Groups →":"Inspect configured AI Identities →"}</button>
    </section>}
    {step===2&&plane==="remote"&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>Why publish a Remote Service?</strong><p>Choose exactly one service/port from an approved Agent. This queues an authenticated Agent job — it does not instantly prove success or user authorization.</p></div>
      <label className="dr-field"><span>Use observed Managed Host as owner</span><select value={selectedHost} disabled={wizardBusy} onChange={e=>chooseRemoteHost(e.target.value)}>
        {!selectedHost&&<option value="">{hosts===null?"Managed Host inventory: UNKNOWN":hosts.length?"Select an observed Managed Host":"No observed Managed Host"}</option>}
        {(hosts||[]).map(h=><option key={h.id} value={String(h.id)}>{h.name||h.label||h.id}</option>)}
      </select></label>
      {!selected?<div className="warning-box dr-uxb-owner-guidance" role="status">
        <strong>Selected Agent must be observed before publishing</strong>
        <p>Choose the intended Agent in Step 1 and refresh Core if its status is UNKNOWN. This guide cannot preview for a typed, unobserved owner.</p>
        <button className="secondary" type="button" disabled={wizardBusy} onClick={()=>setStep(1)}>Go to Agent selection →</button>
      </div>:<p className="dr-uxb-selected-owner" role="status">
        <strong>Publishing for {selected.name||selected.label||selected.hostname||selected.id}</strong>
        <span> · Agent ID {selected.id} · {hostReadinessLabel(selected)}. Connection remains NOT VERIFIED.</span>
      </p>}
      {canEdit&&selected?<RemoteServiceEditor key={selectedHost} api={api} ownerHint={selectedHost} lockOwner
        initialSelection={serviceDraft} resourceCatalog={catalog}
        onBusyChange={setServiceBusy}
        onSelection={s=>{setServiceDraft(s);setServiceName(s.name);if(s.service)setSelector(s.service)}}/>:
       !canEdit?<p className="warning-box">Your role can inspect services but cannot publish them.</p>:null}
      <button className="secondary" onClick={()=>onNavigate?.("services","connections")}>View actual Published Services →</button>
    </div>}
    {step===2&&plane!=="remote"&&<section className="card dr-uxb-choice">
      <h3>{plane==="internet"?"Select the intended outside destination":"Select a named Permission Object"}</h3>
      <p>{plane==="internet"?"Use an approved Network Object/Group for the external destination and a Service Object/Group for its protocol/port."
        :"Choose Permission Object/Group and an AI destination. A permission is not a network port."}</p>
      <div className="dr-uxb-catalog-grid">{plane==="internet"?<>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="destination" value={destination} onChoose={setDestination}/>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="selector" value={selector} onChoose={setSelector}/>
      </>:<>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="selector" value={selector} onChoose={setSelector}/>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="destination" value={destination} onChoose={setDestination}/>
      </>}</div>
      <p className="muted">These are suggestions from existing Core resources, not a new grant. You can edit exact names in the next stage; Core preview validates them.</p>
      <button className="secondary" onClick={()=>onNavigate?.("objects","access",{family:plane==="ai"?"permission":"network"})}>Manage Objects & Groups (advanced) →</button>
    </section>}
    {step===3&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>{plane==="remote"?"Grant only the intended source":"Define the exact intended access"}</strong>
        <p>{plane==="remote"?"An enabled Remote Service is not open until the relevant Remote Access policy permits the source. Use Network/Service Object names, not Agent credentials."
          :plane==="internet"?"Outbound access requires an explicitly selected network source, destination and service. No Remote Service is required."
          :"AI Access uses a verified AI Identity, destination and Permission Object; it is separate from Remote Access."}</p>
      </div>
      {canEdit?<GuidedPolicyJourney key={plane} api={api} initialPlane={plane} lockedPlane resourceCatalog={catalog}
        initialFlow={{source,destination,selector}}
        onFlowChange={f=>{setSource(f.source);setDestination(f.destination);setSelector(f.selector)}} onNavigate={onNavigate}/>:
        <p className="warning-box">Your role is read-only. You can test access but cannot create or apply a rule.</p>}
    </div>}
    {step===4&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>Verify the actual Core decision</strong>
        <p>Enter Network/Service or AI Identity/Permission object names and run a real Core trace. ALLOW is a policy result, not proof a target is reachable. Unknown remains UNKNOWN.</p></div>
      <section className="dr-uxb-catalog-guide"><h3>Choose existing Core resources (or enter exact names below)</h3>
        <div className="dr-uxb-catalog-grid">
          <CoreChoiceField api={api} catalog={catalog} plane={plane} field="source" value={source} onChoose={setSource}/>
          <CoreChoiceField api={api} catalog={catalog} plane={plane} field="destination" value={destination} onChoose={setDestination}/>
          <CoreChoiceField api={api} catalog={catalog} plane={plane} field="selector" value={selector} onChoose={setSelector}/>
        </div>
      </section>
      <div className="dr-uxb-form">
        <label className="dr-field"><span>Source object / identity</span><input value={source} onChange={e=>setSource(e.target.value)} placeholder="Actual Core name"/></label>
        <label className="dr-field"><span>Destination object</span><input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Actual Core name"/></label>
        <label className="dr-field"><span>{plane==="ai"?"Permission":"Service"} Object / Group</span><input value={selector} onChange={e=>setSelector(e.target.value)} placeholder="Actual Core name"/></label>
      </div>
      <AccessEvidenceExplorer api={api} plane={plane} source={source} destination={destination} selector={selector}
        onSelect={f=>{setSource(f.source);setDestination(f.destination);setSelector(f.selector)}} onNavigate={onNavigate}/>
      <p className="muted">To prove end-to-end network reachability, test from the intended client and inspect actual Agent/job/target evidence separately.</p>
    </div>}
  </div>;
}
