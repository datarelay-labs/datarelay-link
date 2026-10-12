import {isObservedAbsoluteTime} from "./uxb-integrations-state";

/** M2/R6: Authorized Core Job detail can contain Agent return payloads,
 * serialized errors, worker IDs, metadata, and credentials. Keep only
 * operational progress fields in the user-facing UI. No backend permission
 * or job-cancellation policy changes.
 */
type DisplayTarget={
  target_id:string,status:string,attempt:number|"UNKNOWN",
  updated_at:string,error:string
};
export type ObservedCoreJobDisplay={
  id:string,job_type:string,status:string,target_count:number,
  resource_type:string,resource_ref:string,deadline_at:string,
  last_error:string,targets:DisplayTarget[]
};
const JOB_TYPES=new Set(["doctor","refresh","version-check","support-bundle",
  "remote-service-set","remote-service-delete","agent-update-rollout"]);
const STATES=new Set(["QUEUED","RUNNING","SUCCEEDED","FAILED","CANCELLED"]);
const ID=/^mjob_[0-9a-f]{24}$/;
const RESOURCE=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const TYPE=/^[a-z][a-z0-9-]{0,63}$/;
const ERROR_CODE=/^[A-Z][A-Z0-9_]{0,63}$/;
const obj=(x:unknown):x is Record<string,any>=>
  !!x&&typeof x==="object"&&!Array.isArray(x);
const code=(x:unknown):string=>
  x===null||x===undefined||x===""?"":typeof x==="string"&&ERROR_CODE.test(x)?x:"UNKNOWN";
const instant=(x:unknown):string=>isObservedAbsoluteTime(x)?x:"UNKNOWN";

export function observedCoreJobDisplay(payload:unknown):ObservedCoreJobDisplay|null{
  if(!obj(payload)||typeof payload.id!=="string"||!ID.test(payload.id)
    ||!JOB_TYPES.has(payload.job_type)||!STATES.has(payload.status)
    ||!Number.isSafeInteger(payload.target_count)
    ||payload.target_count<1||payload.target_count>100
    ||!Array.isArray(payload.targets)
    ||payload.targets.length!==payload.target_count)return null;
  const targets:DisplayTarget[]=[],seen=new Set<string>();
  for(const item of payload.targets){
    if(!obj(item)||typeof item.target_id!=="string"
      ||!RESOURCE.test(item.target_id)||seen.has(item.target_id)
      ||!STATES.has(item.status))return null;
    seen.add(item.target_id);
    targets.push({
      target_id:item.target_id,status:item.status,
      attempt:Number.isSafeInteger(item.attempt)&&item.attempt>=0
        &&item.attempt<=1000000?item.attempt:"UNKNOWN",
      updated_at:instant(item.updated_at),error:code(item.error)
    });
  }
  return {
    id:payload.id,job_type:payload.job_type,status:payload.status,
    target_count:payload.target_count,
    resource_type:typeof payload.resource_type==="string"
      &&TYPE.test(payload.resource_type)?payload.resource_type:"UNKNOWN",
    resource_ref:typeof payload.resource_ref==="string"
      &&RESOURCE.test(payload.resource_ref)?payload.resource_ref:"UNKNOWN",
    deadline_at:instant(payload.deadline_at),last_error:code(payload.last_error),
    targets
  };
}
