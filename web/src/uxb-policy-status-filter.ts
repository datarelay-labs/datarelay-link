/** Local-only PolicyWorkspace status filter. The Core inventory, not the
 * display filter, remains the authorization and completeness authority.
 */
import {policyStateLabel} from "./uxb-menu-evidence";

const ALLOWED=new Set(["all","enabled","disabled","unknown"]);
export function filterObservedPoliciesByStatus<T extends {enabled?:unknown}>(
  items:unknown,status:unknown
):T[]{
  if(!Array.isArray(items)||typeof status!=="string"||!ALLOWED.has(status))return [];
  return items.filter(item=>item!==null&&typeof item==="object"&&!Array.isArray(item)&&
    (status==="all"||policyStateLabel(item.enabled).toLowerCase()===status)) as T[];
}
