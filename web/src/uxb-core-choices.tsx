import React,{useEffect,useRef,useState} from "react";
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

/** Explicit bounded substring search; never assume partial/failing responses are empty.
 * This calls the existing read-only inventory contract, not a new policy API. */
export async function searchCoreSelectorCatalog(
  api:LinkApi,plane:AccessPlane,field:SelectorField,query:string
):Promise<CoreCatalog>{
  const needle=query.trim();
  if(needle.length<2||needle.length>128)throw new Error("Enter at least two and at most 128 characters to find a Core name.");
  const pages=await Promise.all(kinds[plane][field].map(async type=>{
    const url="/api/v1/inventory?resource_type="+encodeURIComponent(type)
      +"&q="+encodeURIComponent(needle)+"&limit=50";
    const page=await api(url);
    if(!Array.isArray(page?.items))throw new Error(type+" Core search response missing items.");
    return [type,{items:page.items,next_cursor:page.next_cursor??null}] as const;
  }));
  return {resources:Object.fromEntries(pages)};
}

/** The same form remains editable: suggestions never replace Core validation. */
export function CoreChoiceField({catalog,plane,field,value,onChoose,disabled=false,api}:{
  catalog:CoreCatalog|null,plane:AccessPlane,field:SelectorField,value:string,disabled?:boolean,
  onChoose:(value:string)=>void,api?:LinkApi,
}){
  const [searchText,setSearchText]=useState("");
  const [searched,setSearched]=useState<CoreCatalog|null>(null);
  const [searchStatus,setSearchStatus]=useState<"idle"|"loading"|"ready"|"error">("idle");
  const [searchError,setSearchError]=useState("");
  const requestGeneration=useRef(0);
  useEffect(()=>{
    // Resource family or authoritative snapshot changed: old matches are not evidence.
    requestGeneration.current+=1;
    setSearched(null);setSearchStatus("idle");setSearchText("");setSearchError("");
  },[plane,field,catalog]);
  useEffect(()=>()=>{requestGeneration.current+=1},[]);
  function editSearch(nextValue:string){
    requestGeneration.current+=1;
    setSearchText(nextValue);setSearched(null);setSearchStatus("idle");setSearchError("");
  }
  async function findCoreNames(e:React.FormEvent){
    e.preventDefault();
    if(!api||disabled||searchText.trim().length<2||searchStatus==="loading")return;
    const generation=++requestGeneration.current;
    setSearched(null);setSearchStatus("loading");setSearchError("");
    try{
      const result=await searchCoreSelectorCatalog(api,plane,field,searchText);
      if(generation!==requestGeneration.current)return;
      setSearched(result);setSearchStatus("ready");
    }catch(err:any){
      if(generation===requestGeneration.current){
        setSearchStatus("error");setSearchError(String(err?.message||err));
      }
    }
  }
  const options=coreSelectorOptions(searchStatus==="ready"?searched:catalog,plane,field);
  const label=labels[plane][field];
  const searchedNames=searchStatus==="ready";
  return <div className="dr-uxb-choice-field">
    <label className="dr-field">
      <span>Choose existing {label}</span>
      <select aria-label={"Choose existing "+label}
        disabled={disabled||searchStatus==="loading"||options.status!=="available"}
        value={options.names.includes(value)?value:""}
        onChange={e=>{if(e.target.value)onChoose(e.target.value)}}>
        <option value="">{options.status==="unknown"?"Core inventory UNKNOWN":
          options.status==="empty"?(searchedNames?"No matching Core names":"No configured options — create one first"):
          searchedNames?"Select a matching Core name…":"Select an existing name…"}</option>
        {options.names.map(name=><option key={name} value={name}>{name}</option>)}
      </select>
    </label>
    <small>{searchedNames?(options.status==="empty"?"No matching names observed. Refine your search or enter an exact name in Advanced.":
      options.truncated?"Matches are limited to 50 per resource type. Narrow the search to find another existing name.":
      "Search matches were read from Core; selecting one does not grant access."):
      options.status==="unknown"?"Suggestions unavailable: check Core status or retry. Exact Core names may still be entered manually.":
      options.status==="empty"?(plane==="ai"&&field==="source"?"No AI Identity is configured in this snapshot. Ask your administrator to provision an identity; this picker cannot create credentials.":"Nothing was returned for this resource type. Open Resources & groups to create one."):
      options.truncated?"Showing a bounded first page. Search for another existing Core name below.":
      "Selected names come from the current Core inventory; this is not an approval or connectivity test."}</small>
    {api&&<form className="dr-uxb-core-search" onSubmit={findCoreNames}>
      <label className="dr-field">
        <span>Find another existing {label}</span>
        <input aria-label={"Search Core "+label} value={searchText}
          disabled={disabled} minLength={2} maxLength={128}
          onChange={e=>editSearch(e.target.value)}
          placeholder="Type at least two characters in the Core name"/>
      </label>
      <div className="dr-uxb-core-search-actions">
        <button type="submit" className="secondary"
          disabled={disabled||searchStatus==="loading"||searchText.trim().length<2}>
          {searchStatus==="loading"?"Searching Core…":"Find matching names"}
        </button>
        {searchedNames&&<button type="button" className="secondary" disabled={disabled}
          onClick={()=>editSearch("")}>Back to first page</button>}
      </div>
      {searchStatus==="error"&&<p className="warning-box" role="alert">Core name search unavailable: {searchError}. Existing options remain unchanged.</p>}
      {searchStatus==="ready"&&<p className="dr-uxb-core-search-count" role="status">
        {options.names.length} matching Core name(s) observed{options.truncated?" · incomplete, narrow search":""}.
      </p>}
    </form>}
    {value&&!options.names.includes(value)&&<small className="dr-uxb-core-selection">
      Current form value: {value}. The visible search list does not verify this name; Core checks it during Preview.
    </small>}
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
