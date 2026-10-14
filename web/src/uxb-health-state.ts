import {isObservedAbsoluteTime} from "./uxb-integrations-state";

/** R2.2/M2: present the bounded read-only Core status projection, never
 * blindly render an arbitrary nested /health JSON object as diagnostic proof.
 * No mutation, privilege elevation or live reachability assertion. */
type Plane="remote"|"internet"|"ai";
const PLANES:Plane[]=["remote","internet","ai"];
const STATES=new Set(["active","not_configured","failed","mismatch"]);
const BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const SENSITIVE=/password|secret|credential|private.?key|api.?key|bearer|token/i;
const object=(value:unknown):value is Record<string,any>=>
  value!==null&&typeof value==="object"&&!Array.isArray(value);
const count=(value:unknown):number|null=>
  typeof value==="number"&&Number.isSafeInteger(value)&&value>=0?value:null;
const errorText=(value:unknown):string=>
  value===""?"":typeof value==="string"&&value.length<=240
    &&!BAD.test(value)&&!SENSITIVE.test(value)?value:"UNKNOWN";

export type ObservedHealthPlane={
 status:string,db_revision:number|null,generation:number|null,
 activated_at:string,error:string
};
export type ObservedHealthJobs={
 active_jobs:number|null,queued_jobs:number|null,running_jobs:number|null,
 failed_jobs:number|null,queued_targets:number|null,running_targets:number|null,
 saturated:boolean|null
};
export type ObservedCoreHealthSnapshot={
 resource:"data-relay-link",read_only:true,db_healthy:boolean,mismatch:boolean,
 schema:number|null,revision:number|null,
 generations:Record<Plane,ObservedHealthPlane>,management_jobs:ObservedHealthJobs
};
export function observedCoreHealthSnapshot(input:unknown):ObservedCoreHealthSnapshot|null{
 if(!object(input)||input.resource!=="data-relay-link"||input.read_only!==true
   ||typeof input.db_healthy!=="boolean"||typeof input.mismatch!=="boolean"
   ||!object(input.generations)||!object(input.management_jobs))return null;
 const generations={} as Record<Plane,ObservedHealthPlane>;
 const revision=count(input.revision);
 for(const plane of PLANES){
   const g=object(input.generations[plane])?input.generations[plane]:{};
   const dbRevision=count(g.db_revision),generation=count(g.generation);
   let status=typeof g.status==="string"&&STATES.has(g.status)?g.status:"UNKNOWN";
   // A purported active runtime at the wrong Core revision does not prove
   // deployed policy health even when a malformed top-level mismatch says no.
   if(status==="active"&&(generation===null||revision===null
     ||generation!==revision||input.mismatch===true))status="UNKNOWN";
   const at=g.activated_at===null||g.activated_at===undefined?"Not observed":
     isObservedAbsoluteTime(g.activated_at)?g.activated_at:"UNKNOWN";
   generations[plane]={status,db_revision:dbRevision,generation,
     activated_at:at,error:errorText(g.error)};
 }
 const j=input.management_jobs;
 let active=count(j.active_jobs),queued=count(j.queued_jobs),
   running=count(j.running_jobs);
 const max=count(j.max_active_jobs);
 const consistent=active!==null&&queued!==null&&running!==null
   &&max!==null&&max>0&&active===queued+running
   &&typeof j.saturated==="boolean"&&j.saturated===(active>=max);
 const saturated=consistent?j.saturated as boolean:null;
 if(!consistent){active=null;queued=null;running=null;}
 return {resource:"data-relay-link",read_only:true,
   db_healthy:input.db_healthy,mismatch:input.mismatch,
   schema:count(input.schema),revision,generations,
   management_jobs:{active_jobs:active,queued_jobs:queued,running_jobs:running,
     failed_jobs:count(j.failed_jobs),queued_targets:count(j.queued_targets),
     running_targets:count(j.running_targets),saturated}};
}

/** Only complete, known Core plane states may produce a configured-plane
 * count. Missing/malformed generations are UNKNOWN rather than zero. */
export function observedHealthPlaneCount(payload:ObservedCoreHealthSnapshot|null):number|null{
 if(!payload)return null;
 const states=PLANES.map(plane=>payload.generations[plane]?.status);
 if(states.some(state=>!STATES.has(state)))return null;
 return states.filter(state=>state==="active").length;
}
