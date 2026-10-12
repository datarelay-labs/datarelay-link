/** M1-B G-36: refresh may only re-read an authorized, successful Core Audit
 * query for the exact page still shown, not an edited-but-unsubmitted draft.
 * Original DRLink display gating; never grants or changes Audit retention.
 */
import {observedAuditAppliedFilters} from "./uxb-audit-context";
const CONTROL=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const safeOpaqueCursor=(value:unknown):value is string=>
  typeof value==="string"&&value.length<=4096&&!CONTROL.test(value);
export function observedAuditPageRefreshAvailable(
 state:unknown,applied:unknown,draft:unknown,position:unknown
):boolean{
 if(state!=="ready"||typeof applied!=="string"||typeof draft!=="string"
    ||applied!==draft||observedAuditAppliedFilters(applied)===null)return false;
 if(!position||typeof position!=="object"||Array.isArray(position))return false;
 const page=position as Record<string,unknown>;
 if(!safeOpaqueCursor(page.cursor)||!Array.isArray(page.history)
    ||page.history.length>100||page.history.some(cursor=>!safeOpaqueCursor(cursor)))return false;
 // Initial page is the only valid position with no cursor.
 if(page.cursor===""&&page.history.length>0)return false;
 return true;
}
