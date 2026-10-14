/** G-31: original, loaded-only sorting of operator-private Saved Views.
 * The Core actor already scoped these first <=100 rows. Sorting is only
 * presentation and never changes Core names, permissions or stored filters.
 */
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

export type SavedViewSortMode="core"|"updated_desc"|"updated_asc";
export function isSavedViewSortMode(value:unknown):value is SavedViewSortMode{
 return value==="core"||value==="updated_desc"||value==="updated_asc";
}
function observedUpdate(value:unknown):number|null{
 if(!value||typeof value!=="object"||Array.isArray(value))return null;
 const time=(value as Record<string,unknown>).updated_at;
 if(!isObservedAbsoluteTime(time))return null;
 const millis=Date.parse(time);
 return Number.isFinite(millis)?millis:null;
}
export function sortLoadedSavedViews<T extends Record<string,unknown>>(
 rows:unknown,mode:unknown
):T[]{
 if(!Array.isArray(rows)||rows.length>100||!isSavedViewSortMode(mode)
   ||rows.some(row=>!row||typeof row!=="object"||Array.isArray(row)))return [];
 const safe=[...rows] as T[];
 if(mode==="core")return safe;
 return safe.map((item,index)=>({item,index,time:observedUpdate(item)}))
   .sort((a,b)=>{
     if(a.time===null)return b.time===null?a.index-b.index:1;
     if(b.time===null)return -1;
     const difference=a.time-b.time;
     return difference===0?a.index-b.index:mode==="updated_asc"?difference:-difference;
   }).map(({item})=>item);
}
