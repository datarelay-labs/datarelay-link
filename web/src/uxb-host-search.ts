// PF-CI: typed filters against the currently observed, authorized Core Host pages.
// This is intentionally NOT a fleet-wide or server-side search contract.
export type ObservedHost=Record<string,unknown>;
export type ObservedHostSearch={
  items:ObservedHost[],applied:boolean,scope:"loaded-only",
  error:string|null,warning:string|null,unknownCount:number
};

const FIELDS:Record<string,string>={
  name:"name",id:"id",host:"hostname",hostname:"hostname",
  status:"status",trust:"trust_status",admission:"admission_state",
  os:"agent_platform",platform:"agent_platform",version:"agent_version",
  connected:"connected",
};
const FREE_FIELDS=["id","name","hostname","status","trust_status",
  "admission_state","agent_platform","agent_version"] as const;
const MISSING_REQUIRES_CORE=new Set(["tag","group","ip"]);
const EXACT_FIELDS=new Set(["status","trust_status","admission_state","connected"]);
// This is the actual Core clients trust enum (trusted/revoked) and the
// SQLite-enforced admission enum. Unknown/new values are incomplete Core
// evidence, never confirmed filter nonmatches or actionable authorization.
const CORE_STATE_VALUES:Record<string,ReadonlySet<string>>={
  trust_status:new Set(["trusted","revoked"]),
  admission_state:new Set(["pending_approval","approved","quarantined"]),
};
const CONTROL=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;

function observedText(row:ObservedHost,key:string):string|null {
  const raw=row[key];
  if(key==="connected"){
    if(raw===true||raw===1)return "connected";
    if(raw===false||raw===0)return "disconnected";
    return null;
  }
  if(typeof raw==="string"){
    const value=raw.trim().toLowerCase();
    if(!value)return null;
    const recognized=CORE_STATE_VALUES[key];
    return recognized&&!recognized.has(value)?null:value;
  }
  // A DB NULL, unrecognized object or absent Agent version cannot
  // be interpreted as a confirmed nonmatch without an evidence caveat.
  return null;
}
function errorResult(items:ObservedHost[],error:string):ObservedHostSearch {
  return {items,applied:false,scope:"loaded-only",error,warning:null,unknownCount:0};
}
export function filterObservedHosts(
  source:unknown,query:unknown,admission:unknown="all"
):ObservedHostSearch {
  if(!Array.isArray(source))return errorResult([],"Core Host inventory was not observed. Retry before searching.");
  // Core Host records must carry an observed stable identity and display name.
  // A partially corrupted page cannot be silently converted to an empty,
  // successfully searched fleet.
  const items=source.filter((item):item is ObservedHost=>
    item!==null&&typeof item==="object"&&!Array.isArray(item)&&
    typeof item.id==="string"&&!!item.id.trim()&&
    typeof item.name==="string"&&!!item.name.trim());
  const invalidCount=source.length-items.length;
  if(invalidCount&&!items.length)
    return errorResult([],"Core Host inventory contained only invalid Host records. Search not applied.");
  if(typeof query!=="string"||query.length>120||CONTROL.test(query))
    return errorResult(items,"Invalid Host search expression. Use at most 120 plain-text characters.");
  // The separate Saved View / UI approval picker must share this same
  // loaded-only evidence check. Otherwise no-text approval filtering turns
  // unknown Core state into a misleading confirmed zero.
  if(admission!=="all"&&(
    typeof admission!=="string"||
    !CORE_STATE_VALUES.admission_state.has(admission.toLowerCase())
  ))return errorResult(items,"Invalid Host admission state. Search not applied.");
  const tokens=query.trim()?query.trim().split(/\s+/):[];
  const filters:{field:string|null,term:string}[]=[];
  for(const token of tokens){
    const separator=token.indexOf(":");
    if(separator>=0){
      const fieldName=token.slice(0,separator).toLowerCase();
      if(!Object.prototype.hasOwnProperty.call(FIELDS,fieldName)){
        const reason=MISSING_REQUIRES_CORE.has(fieldName)
          ?"Core does not expose this field in the Managed Host inventory projection."
          :"Unsupported Host search facet.";
        return errorResult(items,fieldName.slice(0,24)+": not available. "+reason+" Search not applied.");
      }
      let term=token.slice(separator+1).toLowerCase();
      if(!term||term.length>120)
        return errorResult(items,"A typed Host filter needs a nonempty bounded value. Search not applied.");
      const field=FIELDS[fieldName];
      // A typed request for an impossible Core enum cannot legitimately
      // produce "no hosts found" or drive a saved-view claim.
      if(CORE_STATE_VALUES[field]&&!CORE_STATE_VALUES[field].has(term))
        return errorResult(items,"Unsupported Core Host state for "+fieldName+". Search not applied.");
      if(field==="connected"){
        if(["1","true","yes","connected"].includes(term))term="connected";
        else if(["0","false","no","disconnected"].includes(term))term="disconnected";
        else return errorResult(items,"Connection state must be connected/disconnected (true/false). Search not applied.");
      }
      filters.push({field,term});
    }else{
      filters.push({field:null,term:token.toLowerCase()});
    }
  }
  if(admission!=="all")
    filters.push({field:"admission_state",term:(admission as string).toLowerCase()});
  const requiredFields=new Set(filters.filter(f=>f.field).map(f=>f.field as string));
  const hasFreeText=filters.some(f=>f.field===null);
  // Invalid page entries were not valid search candidates; count and disclose
  // them even on a blank query instead of presenting a misleading clean list.
  let unknownCount=invalidCount;
  if(requiredFields.size||hasFreeText){
    for(const row of items){
      // Free-text inspects multiple allowlisted Core fields. If even one of
      // those fields is UNKNOWN, a no-match is not evidence of absence.
      // Do not silently claim the free-text projection is complete.
      if([...requiredFields].some(key=>observedText(row,key)===null)||
         (hasFreeText&&FREE_FIELDS.some(key=>observedText(row,key)===null)))unknownCount++;
    }
  }
  const matches=items.filter(row=>filters.every(f=>
    f.field
      ?(EXACT_FIELDS.has(f.field)
        ?observedText(row,f.field)===f.term
        :(observedText(row,f.field)?.includes(f.term)??false))
      :FREE_FIELDS.some(key=>observedText(row,key)?.includes(f.term)??false)));
  const warning=invalidCount
    ?invalidCount+" invalid/UNKNOWN Core Host record(s) were excluded from this loaded page; the search is incomplete and cannot prove absence."+
      (unknownCount>invalidCount?" "+(unknownCount-invalidCount)+" valid Host(s) also have UNKNOWN requested field values.":"")
    :unknownCount
      ?unknownCount+" loaded Host(s) have UNKNOWN requested field values; an unmatched filter cannot prove absence."
      :null;
  return {items:matches,applied:true,scope:"loaded-only",error:null,warning,unknownCount};
}
