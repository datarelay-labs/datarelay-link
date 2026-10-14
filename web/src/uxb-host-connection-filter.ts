/** Original read-only filtering of exactly the Host inventory already loaded by Core.
 * A missing/invalid Core connected boolean is UNKNOWN, never Disconnected.
 */
import {hostConnectionState} from "./uxb-host-detail";
import type {ObservedHost} from "./uxb-host-search";
export type HostConnectionFilter="all"|"connected"|"disconnected"|"unknown";
export type ObservedHostConnectionFilter={
  items:ObservedHost[],loadedCount:number,unknownCount:number,
  scope:"loaded-only",error:string|null
};
const STATES=new Set(["all","connected","disconnected","unknown"]);
export function filterLoadedHostConnections(
  source:unknown,state:unknown
):ObservedHostConnectionFilter {
  const empty=(message:string):ObservedHostConnectionFilter=>({
    items:[],loadedCount:0,unknownCount:0,scope:"loaded-only",error:message
  });
  if(!Array.isArray(source))return empty("Core Host inventory is unavailable. Connection filter not applied.");
  const valid=source.filter((item):item is ObservedHost=>
    item!==null&&typeof item==="object"&&!Array.isArray(item)&&
    typeof item.id==="string"&&!!item.id.trim()&&
    typeof item.name==="string"&&!!item.name.trim());
  const unknownCount=source.length-valid.length+
    valid.filter(row=>hostConnectionState(row)==="UNKNOWN").length;
  if(typeof state!=="string"||!STATES.has(state))return {
    ...empty("Invalid Host connection state filter."),loadedCount:valid.length,unknownCount
  };
  const items=state==="all"?valid:valid.filter(row=>
    hostConnectionState(row).toLowerCase()===state);
  return {items,loadedCount:valid.length,unknownCount,scope:"loaded-only",error:null};
}
