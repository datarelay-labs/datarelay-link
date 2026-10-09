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
