/** G-15: original, local-only stable sorting of already authorized Host rows.
 * Does not infer runtime/mesh topology, mutate Core inventory or perform I/O.
 */
import {hostVisibleIdentity} from "./uxb-host-detail";
export type HostSortMode="review"|"name_asc"|"name_desc";
const ALLOWED=new Set(["review","name_asc","name_desc"]);
export function isHostSortMode(value:unknown):value is HostSortMode {
  return typeof value==="string"&&ALLOWED.has(value);
}
const collator=new Intl.Collator("en",{sensitivity:"base",numeric:true});
function reviewTier(value:Record<string,unknown>):number {
  return value.admission_state==="PENDING_APPROVAL"?0:
    value.admission_state==="QUARANTINED"?1:2;
}
function displayName(row:Record<string,unknown>):string {
  return hostVisibleIdentity(row).primary;
}
export function sortLoadedHosts(
  source:unknown,mode:unknown
):Record<string,unknown>[]{
  if(!Array.isArray(source)||!isHostSortMode(mode))return [];
  const valid=source.filter((item):item is Record<string,unknown>=>
    item!==null&&typeof item==="object"&&!Array.isArray(item)&&
    typeof item.id==="string"&&!!item.id.trim());
  const ranked=valid.map((row,i)=>({row,i}));
  ranked.sort((a,b)=>{
    if(mode==="review")return reviewTier(a.row)-reviewTier(b.row)||a.i-b.i;
    const diff=collator.compare(displayName(a.row),displayName(b.row));
    return (mode==="name_asc"?diff:-diff)||a.i-b.i;
  });
  return ranked.map(item=>item.row);
}
