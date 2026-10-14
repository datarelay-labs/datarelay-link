/** M1-B G-22: original, local-only Policy → Audit investigation context.
 * Policy data must already have been returned in the authorized Core policy
 * list. The destination independently checks the Audit API and access rights.
 * Do not infer a matching Audit event, policy grant, or request approval.
 */
import {observedPolicyDetailFields} from "./uxb-policy-expiry";

type AccessPlane="remote"|"internet"|"ai";
export type PolicyAuditTarget={
 originType:"access-rule",originId:string,plane:AccessPlane
};
const PLANES=new Set(["remote","internet","ai"]);
export function policyAuditInvestigationTarget(row:unknown):PolicyAuditTarget|null{
 if(!row||typeof row!=="object"||Array.isArray(row))return null;
 const policy=row as Record<string,unknown>;
 if(typeof policy.plane!=="string"||!PLANES.has(policy.plane))return null;
 // The existing fixed-field read-only projector rejects missing/unsafe IDs,
 // bad Core shapes and Unicode control/bidi ambiguity.
 const validated=observedPolicyDetailFields(policy);
 const id=validated.find(field=>field.label==="Policy ID")?.value;
 if(typeof id!=="string"||id!==policy.id)return null;
 return {originType:"access-rule",originId:id,plane:policy.plane as AccessPlane};
}
