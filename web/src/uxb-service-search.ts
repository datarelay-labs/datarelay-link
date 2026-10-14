import {serviceStateLabel} from "./uxb-service-detail";

/** Search only current authorized Core inventory pages. No arbitrary keys,
 * secrets, server-side discovery, DNS probing or inferred fleet completeness.
 */
export type ServiceSearchResult={
  items:Record<string,unknown>[],applied:boolean,scope:"loaded-only",
  error:string|null,warning:string|null,unknownCount:number
};
type ServiceRow=Record<string,unknown>;
const BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const ALLOWED=new Set(["name","id","host","type","target","port","state"]);
const FREE_FIELDS=["name","id","managed_host","managed_host_id",
  "service_type","target_host","target_mode","public_port","target_port"] as const;

function errorResult(items:ServiceRow[],reason:string):ServiceSearchResult{
 return {items,applied:false,scope:"loaded-only",error:reason,warning:null,unknownCount:0};
}
function observedText(row:ServiceRow,key:string):string|null{
 const raw=row[key];
 if(key==="public_port"||key==="target_port"){
   return typeof raw==="number"&&Number.isSafeInteger(raw)&&raw>=1&&raw<=65535
     ?String(raw):null;
 }
 if(typeof raw!=="string"||BAD.test(raw))return null;
 const text=raw.trim().toLowerCase();
 return text||null;
}
function fields(row:ServiceRow,facet:string):Array<string|null>{
 if(facet==="host")return [observedText(row,"managed_host"),observedText(row,"managed_host_id")];
 if(facet==="target")return [observedText(row,"target_host"),observedText(row,"target_mode")];
 if(facet==="port")return [observedText(row,"public_port"),observedText(row,"target_port")];
 if(facet==="type")return [observedText(row,"service_type")];
 if(facet==="state"){
  const value=serviceStateLabel(row);
  return [value==="UNKNOWN"?null:value.toLowerCase()];
 }
 return [observedText(row,facet)];
}
export function filterObservedServices(source:unknown,query:unknown):ServiceSearchResult{
 if(!Array.isArray(source))return errorResult([],"Core Remote Service inventory unavailable. Retry the Core read.");
 const items=source.filter((row):row is ServiceRow=>
  row!==null&&typeof row==="object"&&!Array.isArray(row)&&
  typeof row.id==="string"&&!!row.id.trim()&&
  typeof row.name==="string"&&!!row.name.trim());
 const invalidCount=source.length-items.length;
 if(invalidCount&&!items.length)
   return errorResult([],"All returned Core Remote Service records were invalid. Search not applied.");
 if(typeof query!=="string"||query.length>120||BAD.test(query))
   return errorResult(items,"Invalid Service search expression. Use at most 120 safe text characters.");
 const tokens=query.trim()?query.trim().split(/\s+/):[];
 const filters:Array<{facet:string|null,term:string}>=[];
 for(const token of tokens){
   const colon=token.indexOf(":");
   if(colon<0){filters.push({facet:null,term:token.toLowerCase()});continue;}
   const facet=token.slice(0,colon).toLowerCase(),term=token.slice(colon+1).toLowerCase();
   if(!ALLOWED.has(facet))return errorResult(items,
     facet.slice(0,24)+": unsupported Core Service field. Search not applied.");
   if(!term||term.length>120)return errorResult(items,
     "A Service filter needs a bounded nonempty value. Search not applied.");
   if(facet==="port"&&(!/^\d+$/.test(term)||Number(term)<1||Number(term)>65535))
     return errorResult(items,"Port must be an explicit integer from 1 to 65535. Search not applied.");
   if(facet==="state"&&!["enabled","disabled","released"].includes(term))
     return errorResult(items,"Service state must be enabled, disabled or released. Search not applied.");
   filters.push({facet,term});
 }
 const matchFilter=(row:ServiceRow,filter:{facet:string|null,term:string}):boolean=>{
  if(filter.facet==="port")return fields(row,"port").some(v=>v===String(Number(filter.term)));
  if(filter.facet==="state")return fields(row,"state")[0]===filter.term;
  if(filter.facet)return fields(row,filter.facet).some(v=>v?.includes(filter.term)??false);
  return FREE_FIELDS.some(k=>observedText(row,k)?.includes(filter.term)??false)||
    (serviceStateLabel(row)!=="UNKNOWN"&&serviceStateLabel(row).toLowerCase().includes(filter.term));
 };
 // An absent alternative field cannot prove a negative match:
 // host name may differ while Host ID is unobserved; public port may
 // differ while target port is unobserved. Only nonmatches need a warning.
 const unknownFor=(row:ServiceRow,filter:{facet:string|null,term:string}):boolean=>
   !matchFilter(row,filter) &&
   (filter.facet?fields(row,filter.facet).some(v=>v===null):
     FREE_FIELDS.some(key=>observedText(row,key)===null)||
       serviceStateLabel(row)==="UNKNOWN");
 let unknownCount=invalidCount;
 if(filters.length)unknownCount+=items.filter(row=>filters.some(f=>unknownFor(row,f))).length;
 const matches=items.filter(row=>filters.every(filter=>matchFilter(row,filter)));
 const warning=invalidCount||unknownCount?
   (invalidCount?invalidCount+" invalid Core records excluded. ":"")+
   (unknownCount>invalidCount?(unknownCount-invalidCount)+" loaded Remote Service records contain UNKNOWN requested facts. ":"")+
   "An unmatched filter cannot prove absence beyond observed Core pages.":null;
 return {items:matches,applied:true,scope:"loaded-only",error:null,warning,unknownCount};
}
