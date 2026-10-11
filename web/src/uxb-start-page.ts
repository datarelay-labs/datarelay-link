/** G-14: per-authenticated-actor, role-scoped browser-only start-page preference.
 * Route IDs are not permission grants; all choices pass Core Web role gating.
 * Never persist credentials, tokens, sessions or navigation contexts.
 */
import {visibleRoute} from "./uxb-navigation";

export const START_PAGE_OPTIONS=[
 {id:"overview",label:"Home"},
 {id:"hosts",label:"Servers & Agents"},
 {id:"services",label:"Published services"},
 {id:"policies",label:"Access rules"},
 {id:"access",label:"Test & explain access"},
 {id:"health",label:"System health"},
 {id:"audit",label:"Activity log"},
 {id:"jobs",label:"Jobs"},
 {id:"views",label:"Saved Views"},
 {id:"users",label:"Users & MFA (Admin)"},
] as const;
export type StartPageId=typeof START_PAGE_OPTIONS[number]["id"];
type Actor={id:string,role:"Admin"|"Operator"|"Read Only"};
type BrowserStore={getItem:(key:string)=>string|null,setItem:(key:string,value:string)=>void};
const ROLES=new Set(["Admin","Operator","Read Only"]);
const ALLOWED=new Set<string>(START_PAGE_OPTIONS.map(option=>option.id));
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;

function exactActor(value:unknown):Actor|null{
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const obj=value as Record<string,unknown>;
  return typeof obj.id==="string"&&ID.test(obj.id)&&
    typeof obj.role==="string"&&ROLES.has(obj.role)
      ?{id:obj.id,role:obj.role as Actor["role"]}:null;
}
function routeAllowed(actor:Actor,route:unknown):route is StartPageId{
  return typeof route==="string"&&ALLOWED.has(route)&&visibleRoute(route,actor.role);
}
export function startPageKeyForOperator(value:unknown):string|null{
  const actor=exactActor(value);
  return actor?"drlink_web_start_page_v1:"+actor.id+":"+actor.role:null;
}
function storeLike(value:unknown):BrowserStore|null{
  return !!value&&typeof value==="object"&&
    typeof (value as BrowserStore).getItem==="function"&&
    typeof (value as BrowserStore).setItem==="function"
      ?value as BrowserStore:null;
}
export function readPreferredStartPage(actorInput:unknown,storeInput:unknown):StartPageId{
  const actor=exactActor(actorInput),key=startPageKeyForOperator(actorInput);
  if(!actor||!key)return "overview";
  try {
    const store=storeLike(storeInput);
    const value=store?.getItem(key);
    return routeAllowed(actor,value)?value:"overview";
  }catch{return "overview";}
}
export function writePreferredStartPage(actorInput:unknown,route:unknown,storeInput:unknown):boolean{
  const actor=exactActor(actorInput),key=startPageKeyForOperator(actorInput);
  if(!actor||!key||!routeAllowed(actor,route))return false;
  try{
    const store=storeLike(storeInput);
    if(!store)return false;
    store.setItem(key,route);
    return store.getItem(key)===route;
  }catch{return false;}
}
