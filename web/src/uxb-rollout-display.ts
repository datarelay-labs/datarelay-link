import {requireObservedRolloutPreview} from "./uxb-menu-evidence";

/** M2/R6: even after matching the Core read-only Preview request, values
 * sourced from Agent inventory are not trusted presentation text.
 * Never upgrade the source's NOT_VERIFIED artifact identity into Apply
 * authority. Do not export nested Core/Agent records to the browser view.
 */
const RESOURCE=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const VERSION=/^[A-Za-z0-9][A-Za-z0-9._+:-]{0,63}$/;
const PLATFORM=/^[A-Za-z0-9][A-Za-z0-9._+:-]{0,63}$/;
export function observedRolloutPreviewDisplay(payload:unknown,request:unknown):any|null{
 let core:any;
 try{core=requireObservedRolloutPreview(payload,request)}catch{return null}
 const art=core.artifact;
 if(!VERSION.test(art.version)
   ||core.targets.some((id:unknown)=>typeof id!=="string"||!RESOURCE.test(id))
   ||core.canary_targets.some((id:unknown)=>typeof id!=="string"||!RESOURCE.test(id))
   ||core.blocked_targets.some((id:unknown)=>typeof id!=="string"||!RESOURCE.test(id)))
   return null;
 const observations=core.target_observations.map((row:any)=>{
   const version=VERSION.test(row.current_version)?row.current_version:"UNKNOWN";
   const platform=PLATFORM.test(row.platform)?row.platform:"UNKNOWN";
   // If an Agent-supplied version is unfit for display, its comparison
   // cannot become positive/negative rollout evidence.
   const relation=version==="UNKNOWN"?"UNKNOWN":row.version_relation;
   return {
     target_id:row.target_id,
     current_version:version,target_version:art.version,platform,
     version_relation:relation,provenance:"NOT_VERIFIED",update_available:"UNKNOWN"
   };
 });
 return {
   read_only:true,eligible:core.eligible,ready_to_apply:false,creates_job:false,
   artifact_qualification:"NOT_VERIFIED",
   qualification_note:"Actual Agent artifact provenance, signatures, updater and rollback are NOT VERIFIED.",
   requires_fresh_validation_on_apply:true,
   targets:[...core.targets],target_count:core.target_count,
   blocked_targets:[...core.blocked_targets],
   canary_targets:[...core.canary_targets],
   wave_size:core.wave_size,failure_threshold_percent:core.failure_threshold_percent,
   artifact:{version:art.version,source_ref:art.source_ref,sha256:art.sha256},
   target_observations:observations
 };
}
