/** M1-A G-19: original presentation projection for already authorized
 * loaded Host/Service rows. Never derive access, reachability or secrets.
 * Reuses the existing DataRelay allowlisted detail and status projections.
 */
import {hostVisibleIdentity,hostConnectionState,hostInventoryFacts} from "./uxb-host-detail";
import {serviceVisibleIdentity,serviceStateLabel,serviceDetailSections} from "./uxb-service-detail";

export type ResourceCardFact={label:string,value:string};
export type ResourceCardSummary={
 title:string,subtitle:string,status:string,facts:ResourceCardFact[]
};
function observedRecord(input:unknown):Record<string,unknown>|null {
 if(input===null||typeof input!=="object"||Array.isArray(input))return null;
 const row=input as Record<string,unknown>;
 return typeof row.id==="string"&&!!row.id.trim()?row:null;
}
function hostAdmission(row:Record<string,unknown>):string{
 return row.admission_state==="APPROVED"?"Approved":
   row.admission_state==="PENDING_APPROVAL"?"Pending approval":
   row.admission_state==="QUARANTINED"?"Quarantined":"UNKNOWN";
}
export function resourceCardSummary(
 kind:unknown,input:unknown
):ResourceCardSummary|null{
 const row=observedRecord(input);
 if(!row)return null;
 if(kind==="host"){
   const name=hostVisibleIdentity(row),facts=hostInventoryFacts(row);
   return {title:name.primary,subtitle:name.secondary,
     status:hostConnectionState(row),
     facts:[
       {label:"Admission",value:hostAdmission(row)},
       {label:"Trust",value:facts.trust},
       {label:"Agent heartbeat",value:facts.lastHeartbeat}
     ]};
 }
 if(kind==="service"){
   const name=serviceVisibleIdentity(row);
   // The existing Service detail projector has the explicit Core field
   // allowlist, field-specific sanitization and validated public-port bounds.
   const fields=serviceDetailSections(row).flatMap(section=>section.fields);
   const observed=(label:string)=>fields.find(field=>field.label===label)?.value||"UNKNOWN";
   return {title:name.primary,subtitle:name.secondary,
     status:serviceStateLabel(row),
     facts:[
       {label:"Managed Host",value:observed("Managed Host")},
       {label:"Service type",value:observed("Service type")},
       {label:"Public port",value:observed("Public port")}
     ]};
 }
 return null;
}
