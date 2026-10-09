/** UXB-06F: a successful HTTP response is not automatically a valid, empty Core page.
 * Each listed menu must receive its canonical collection before showing "No results".
 * This changes Web presentation only; the Server/Core remains the authority. */
const collectionPages:Record<string,string>={
  hosts:"Servers & Agents",
  services:"Published services",
  policies:"Access rules",
  enrollments:"Agent enrollments",
  hygiene:"Access hygiene",
  jobs:"Management Jobs",
  audit:"Activity log",
  users:"Web Users",
  "service-accounts":"Service Accounts",
  webhooks:"Signed Event Webhooks",
  revisions:"Change history",
  views:"Saved views",
};

/** A page with a Core cursor is not a complete inventory; local filters only
 * check loaded rows and may not find the rest. */
export function isPartialCorePage(payload:any):boolean{
  return typeof payload?.next_cursor==="string"&&payload.next_cursor.length>0;
}

/** Keyset page navigation only uses observed opaque Core cursors. The UI may
 * navigate backwards using previous request cursors; it never guesses a total. */
export type MenuPagePosition={cursor:string,history:string[]};
export function selectMenuPage(
  current:MenuPagePosition, nextCursor:unknown, direction:"older"|"newer"|"reset"
):MenuPagePosition|null{
  if(direction==="reset")return {cursor:"",history:[]};
  if(direction==="older"){
    if(typeof nextCursor!=="string"||!nextCursor||nextCursor===current.cursor)return null;
    return {cursor:nextCursor,history:[...current.history,current.cursor]};
  }
  if(!current.history.length)return null;
  return {cursor:current.history[current.history.length-1],
    history:current.history.slice(0,-1)};
}

/** Fetch each policy plane separately: a single all-plane 100-row limit can
 * hide an entire later plane behind earlier Remote rules. Keep the limit honest. */
export function combineObservedPolicyPlanes(
  pages:unknown[],limit:number
):{items:any[],possibly_truncated_planes:string[],next_cursor_by_plane:Record<string,string|null>}{
  const planes=["remote","internet","ai"] as const;
  if(!Array.isArray(pages)||pages.length!==planes.length
    ||!Number.isSafeInteger(limit)||limit<1)
    throw new Error("Core policy plane inventory is incomplete. State is UNKNOWN.");
  const items:any[]=[],possibly_truncated_planes:string[]=[];
  const next_cursor_by_plane:Record<string,string|null>={};
  for(let i=0;i<planes.length;i++){
    const page=requireObservedMenuPayload("policies",pages[i]);
    if(page.plane!==planes[i]||page.limit!==limit
      ||page.items.length>limit
      ||page.items.some((item:any)=>item.plane!==planes[i]))
      throw new Error("Core "+planes[i]+" policy response is inconsistent. State is UNKNOWN.");
    items.push(...page.items);
    // New Core supports real per-plane next_cursor. A legacy response that
    // exactly reaches the limit must still be marked potentially incomplete.
    const hasCursor=Object.prototype.hasOwnProperty.call(page,"next_cursor");
    next_cursor_by_plane[planes[i]]=isPartialCorePage(page)?page.next_cursor:null;
    if(page.items.length===limit&&(!hasCursor||!!page.next_cursor))
      possibly_truncated_planes.push(planes[i]);
  }
  return {items,possibly_truncated_planes,next_cursor_by_plane};
}

export function requireObservedMenuPayload(route:string,payload:unknown):any{
  if(payload===null||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("Core response unavailable or malformed. Page state is UNKNOWN; retry the read.");
  const value=payload as Record<string,unknown>;
  if(Object.prototype.hasOwnProperty.call(value,"next_cursor")
    &&value.next_cursor!==null&&typeof value.next_cursor!=="string")
    throw new Error("Core pagination cursor is malformed. Loaded entries may be incomplete; state is UNKNOWN.");
  const collection=collectionPages[route];
  if(collection&&!Array.isArray(value.items))
    throw new Error(collection+" Core API response is missing an items list. State is UNKNOWN, not an empty list; retry or check System health.");
  if(collection&&(value.items as unknown[]).some(row=>
    !row||typeof row!=="object"||Array.isArray(row)))
    throw new Error(collection+" Core API returned invalid resource entries. State is UNKNOWN; retry or check System health.");
  if(route==="doctor"&&!Array.isArray(value.checks))
    throw new Error("Troubleshooting Core API response is missing checks. State is UNKNOWN; retry or check System health.");
  if(route==="versions"&&!Array.isArray(value.hosts))
    throw new Error("Agent versions Core API response is missing hosts. State is UNKNOWN; retry or check System health.");
  if(route==="overview"&&(!value.overview||typeof value.overview!=="object"||Array.isArray(value.overview)))
    throw new Error("Home Core overview is unavailable. State is UNKNOWN; retry or check System health.");
  return payload;
}
