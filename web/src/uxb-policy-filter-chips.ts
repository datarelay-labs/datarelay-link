/** G-24: original PolicyWorkspace active local filter summary. Core remains
 * authoritative for policy/security state; the UI never echoes raw search.
 * AGPL competitor source/assets are research evidence only, not dependencies.
 */
export type PolicyFilterChipId="plane"|"search"|"status"|"expiry"|"sort";
export type PolicyFilterChip={id:PolicyFilterChipId,label:string,value:string};
const PLANE:Record<string,string>={remote:"Remote",internet:"Internet",ai:"AI"};
const STATE:Record<string,string>={enabled:"Enabled",disabled:"Disabled",unknown:"UNKNOWN"};
const EXPIRY:Record<string,string>={expired:"Expired",due24h:"Due within 24h",
 later:"Later",never:"Never",unknown:"UNKNOWN"};
const SORT:Record<string,string>={name_asc:"Policy name A–Z",name_desc:"Policy name Z–A"};
function bounded(value:unknown,known:Record<string,string>):string{
 return typeof value==="string"&&Object.prototype.hasOwnProperty.call(known,value)
  ?known[value]:"UNKNOWN";
}
export function activePolicyFilterChips(
 plane:unknown,search:unknown,status:unknown,expiry:unknown,sort:unknown
):PolicyFilterChip[]{
 const chips:PolicyFilterChip[]=[];
 if(plane!=="all")chips.push({id:"plane",label:"Plane",value:bounded(plane,PLANE)});
 if(typeof search!=="string")chips.push({id:"search",label:"Search",value:"UNKNOWN"});
 else if(search.trim())chips.push({id:"search",label:"Search",value:"Active"});
 if(status!=="all")chips.push({id:"status",label:"State",value:bounded(status,STATE)});
 if(expiry!=="all")chips.push({id:"expiry",label:"Expiry",value:bounded(expiry,EXPIRY)});
 if(sort!=="core")chips.push({id:"sort",label:"Sort",value:bounded(sort,SORT)});
 return chips;
}
