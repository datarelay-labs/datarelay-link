import React,{useEffect,useState} from "react";
import type {LinkApi,AccessPlane} from "./p0-access-policy";

/** Bounded, read-only suggestions from the real Core Objects & Groups API.
 * Display names only; never infer a Host is a Network Object or grant access. */
export type CoreCatalog={resources:Record<string,{items?:any[],next_cursor?:string|null}>};
export type SelectorField="source"|"destination"|"selector";

const kinds:Record<AccessPlane,Record<SelectorField,readonly string[]>>={
  remote:{
    source:["network-object","network-group"],
    destination:["network-object","network-group"],
    selector:["service-object","service-group"],
  },
  internet:{
    source:["network-object","network-group"],
    destination:["network-object","network-group"],
    selector:["service-object","service-group"],
  },
  ai:{
    source:["ai-identity"],
    destination:["network-object","network-group"],
    selector:["permission-object","permission-group"],
  },
};
const labels:Record<AccessPlane,Record<SelectorField,string>>={
  remote:{source:"Source Network Object / Group",destination:"Destination Network Object / Group",selector:"Service Object / Group"},
  internet:{source:"Protected source Network Object / Group",destination:"Outside destination Network Object / Group",selector:"Service Object / Group"},
  ai:{source:"AI Identity",destination:"AI destination Network Object / Group",selector:"Permission Object / Group"},
};

export function coreSelectorOptions(catalog:CoreCatalog|null,plane:AccessPlane,field:SelectorField){
  const types=kinds[plane][field];
  if(!catalog?.resources||types.some(type=>!Array.isArray(catalog.resources[type]?.items)))
    return {status:"unknown" as const,names:[] as string[],truncated:false};
  const names=[...new Set(types.flatMap(type=>catalog.resources[type].items||[])
    .map(row=>typeof row?.name==="string"?row.name.trim():"").filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  return {
    status:(names.length?"available":"empty") as "available"|"empty",
    names,truncated:types.some(type=>!!catalog.resources[type]?.next_cursor),
  };
}

/** The same form remains editable: suggestions never replace Core validation. */
export function CoreChoiceField({catalog,plane,field,value,onChoose,disabled=false}:{
  catalog:CoreCatalog|null,plane:AccessPlane,field:SelectorField,value:string,disabled?:boolean,
  onChoose:(value:string)=>void,
}){
  const options=coreSelectorOptions(catalog,plane,field);
  const label=labels[plane][field];
  return <div className="dr-uxb-choice-field">
    <label className="dr-field">
      <span>Choose existing {label}</span>
      <select aria-label={"Choose existing "+label}
        disabled={disabled||options.status!=="available"}
        value={options.names.includes(value)?value:""}
        onChange={e=>{if(e.target.value)onChoose(e.target.value)}}>
        <option value="">{options.status==="unknown"?"Core inventory UNKNOWN":
          options.status==="empty"?"No configured options — create one first":"Select an existing name…"}</option>
        {options.names.map(name=><option key={name} value={name}>{name}</option>)}
      </select>
    </label>
    <small>{options.status==="unknown"?"Suggestions unavailable: check Core status or retry. Exact Core names may still be entered manually.":
      options.status==="empty"?(plane==="ai"&&field==="source"?"No AI Identity is configured in this snapshot. Ask your administrator to provision an identity; this picker cannot create credentials.":"Nothing was returned for this resource type. Open Resources & groups to create one."):
      options.truncated?"Showing a bounded first page. Other valid names can be typed manually.":
      "Selected names come from the current Core inventory; this is not an approval or connectivity test."}</small>
  </div>;
}

/** Fetch only public management names. Caller-provided catalog avoids duplicate fetches in Setup. */
export function useCoreCatalog(api:LinkApi,provided?:CoreCatalog|null):CoreCatalog|null{
  const [fetched,setFetched]=useState<CoreCatalog|null>(null);
  useEffect(()=>{
    if(provided!==undefined)return;
    let active=true;
    api("/api/v1/objects-groups?limit=50").then(result=>{
      if(active)setFetched(result?.resources&&typeof result.resources==="object"?result as CoreCatalog:null);
    }).catch(()=>{if(active)setFetched(null)});
    return()=>{active=false};
  },[api,provided]);
  return provided===undefined?fetched:provided;
}
