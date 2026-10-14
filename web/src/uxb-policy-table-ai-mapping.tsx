/** M1-B G-26: configured AI Policy Core references in the default Web table.
 * This is display-only for authorized Core-loaded policies, not a policy
 * decision, network topology, reviewer approval or actual active permission.
 * Independent DRLink implementation; NetBird AGPL source is research only.
 */
import React from "react";
import {observedPolicyCardSummary} from "./uxb-policy-cards";

export type ObservedAiPolicyTableMapping={
 source:string,destination:string,permission:string
};
export function observedAiPolicyTableMapping(
 row:unknown,asOf:unknown
):ObservedAiPolicyTableMapping|null{
 if(!row||typeof row!=="object"||Array.isArray(row))return null;
 if((row as Record<string,unknown>).plane!=="ai")return null;
 // G-25 already sanitizes the precise source/target/permission Core whitelist,
 // validates the policy ID and refuses nested, unsafe or absent references.
 const summary=observedPolicyCardSummary(row,asOf);
 if(!summary||summary.plane!=="AI")return null;
 const get=(label:string)=>summary.facts.find(fact=>fact.label===label)?.value||"UNKNOWN";
 return {
  source:get("Source identity"),
  destination:get("Destination reference"),
  permission:get("Permission reference")
 };
}

export function AiPolicyMappingCell({row,asOf}:{row:unknown,asOf:unknown}){
 if(!row||typeof row!=="object"||Array.isArray(row)||
    (row as Record<string,unknown>).plane!=="ai")
   return <span className="muted">Not provided by Core</span>;
 const mapping=observedAiPolicyTableMapping(row,asOf);
 if(!mapping)return <span className="muted">UNKNOWN · Core policy identity unverified</span>;
 return <div className="dr-policy-ai-mapping" role="group"
   aria-label="AI policy Core references">
   <span>Source identity: <strong>{mapping.source}</strong></span>
   <span>Destination reference: <strong>{mapping.destination}</strong></span>
   <span>Permission reference: <strong>{mapping.permission}</strong></span>
 </div>;
}
