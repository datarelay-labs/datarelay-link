/** G-17: original local-only active Host display filter summary.
 * Never echo typed queries, untrusted enum values or credentials into chips.
 */
export type HostFilterChipId="search"|"admission"|"connection"|"sort";
export type HostFilterChip={
  id:HostFilterChipId,label:string,value:string
};
const ADMISSION:Record<string,string>={
  APPROVED:"Approved",
  PENDING_APPROVAL:"Pending approval",
  QUARANTINED:"Quarantined"
};
const CONNECTION:Record<string,string>={
  connected:"Connected",
  disconnected:"Disconnected",
  unknown:"UNKNOWN"
};
const SORT:Record<string,string>={
  name_asc:"Host name A–Z",
  name_desc:"Host name Z–A"
};
function knownValue(source:unknown,map:Record<string,string>):string {
  return typeof source==="string"&&Object.prototype.hasOwnProperty.call(map,source)
    ?map[source]:"UNKNOWN";
}
export function activeHostFilterChips(
  search:unknown,admission:unknown,connection:unknown,sort:unknown
):HostFilterChip[]{
  const chips:HostFilterChip[]=[];
  if(typeof search!=="string")
    chips.push({id:"search",label:"Search",value:"UNKNOWN"});
  else if(search.trim())
    chips.push({id:"search",label:"Search",value:"Active"});
  if(admission!=="all")
    chips.push({id:"admission",label:"Admission",value:knownValue(admission,ADMISSION)});
  if(connection!=="all")
    chips.push({id:"connection",label:"Connection",value:knownValue(connection,CONNECTION)});
  if(sort!=="review")
    chips.push({id:"sort",label:"Sort",value:knownValue(sort,SORT)});
  return chips;
}
