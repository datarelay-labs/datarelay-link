/**
 * DRL3-7B: product presentation vocabulary only. IDs are the existing
 * Web/Core routes; this file never changes authorization or policy semantics.
 */
/** Only AI Identity and Permission selectors are unique to AI Access.
 * Network/Service objects are shared by Remote and Internet; never guess. */
export function setupContextForObjectFamily(family:string):{plane:"ai"}|null{
  return family==="ai"||family==="permission"?{plane:"ai"}:null;
}

export const navGroups = [
  {id:"connections",label:"Connections",description:"Servers and services you intentionally connect",items:[
    ["hosts","Servers & Agents"],["services","Published services"],
  ]},
  {id:"access",label:"Access",description:"Define and explain who may connect",items:[
    ["policies","Access rules"],["access","Test & explain access"],["objects","Resources & groups · Advanced"],
  ]},
  {id:"activity",label:"Activity & Health",description:"Find problems, audit decisions and track changes",items:[
    ["health","System health"],["hygiene","Attention & troubleshooting"],["audit","Activity log"],
    ["jobs","Jobs"],["versions","Agent version drift · Advanced"],["revisions","Change history"],["views","Saved Views"],
  ]},
  {id:"administration",label:"Administration",description:"Operator accounts and product settings",items:[
    ["system","System administration"],["users","Users & MFA"],["integrations","Integrations"],
  ]},
] as const;

export const contextualRoutes = [
  {id:"enrollments",label:"Add a server / Agent",group:"connections",description:"Install, enroll and approve a new Agent"},
  {id:"setup",label:"Set up a connection",group:"connections",description:"One guided path from Agent to narrow access"},
  {id:"drafts",label:"Advanced configuration draft",group:"access",description:"Core-backed ConfigurationBundle test, preview and apply"},
  {id:"doctor",label:"Troubleshoot",group:"activity",description:"Investigate a specific system error"},
] as const;

export const pageDescriptions: Record<string,string> = {
  overview:"Your current status, setup progress and next safe action",
  hosts:"Servers that have the DRLink Agent; enrolled, trusted and connected are different",
  services:"Individual internal services you choose to publish, not an entire network",
  objects:"Canonical Network, Service and Permission Objects / Groups used by rules",
  policies:"Choose Remote, Internet or AI Access and preview changes before applying",
  access:"Ask the Core why a source can or cannot reach a destination",
  health:"Core, agent and policy-engine status backed by observed data",
  hygiene:"Items that may need attention; unknown evidence is not automatically healthy",
  audit:"Who acted on what, when and with what result",
  jobs:"Background operations and their actual completion status",
  revisions:"A history of configuration changes, not live connection status",
  versions:"Compare observed Agent versions with the expected release",
  system:"Shared product settings and separate Core-owned advanced actions",
  users:"Admin-only user accounts, roles and per-user MFA",
  integrations:"Admin-only service accounts and signed Webhook destinations",
  enrollments:"Four-stage Agent invitation, installation, approval and verification",
  setup:"Guided connection setup with separate Remote / Internet / AI semantics",
  drafts:"Advanced ConfigurationBundle editor; changes still require Core confirmation",
  doctor:"Run diagnostics and inspect actual Core evidence",
  views:"Saved resource filters; not access permissions",
};

export const oldAliases: Record<string,string[]> = {
  overview:["overview","dashboard","command center","home"],
  hosts:["infrastructure","managed hosts","agent inventory","hosts","servers"],
  services:["remote services","published services","infrastructure","ssh","rdp"],
  objects:["objects & groups","network objects","service objects","permission objects","resource groups"],
  policies:["policies","policy editor","access control","whitelist","blacklist"],
  access:["access operations","policy simulator","diagnose","decision trace","test connection"],
  health:["observability","health","system health","core status"],
  hygiene:["access hygiene","orphaned objects","attention"],
  audit:["observability","audit","access log"],
  jobs:["operations","jobs","management jobs"],
  revisions:["revisions","operations","configuration changes"],
  versions:["version drift","versions","operations"],
  system:["system","system admin","system settings"],
  users:["users","accounts","mfa","administration"],
  integrations:["integrations","webhooks","service accounts","administration"],
  enrollments:["connect agent","enrollment","install agent","onboarding"],
  setup:["first connection","guided setup","getting started","new connection","connect ssh"],
  drafts:["draft workspace","configuration bundle","raw editor"],
  doctor:["doctor","troubleshoot","troubleshooting"],
  views:["saved views","saved filters"],
};

export function visibleRoute(id:string,role:string):boolean {
  if(["users","integrations","enrollments"].includes(id))return role==="Admin";
  if(id==="drafts")return role!=="Read Only";
  return true;
}
export function groupFor(id:string):string {
  const group=navGroups.find(g=>g.items.some(item=>item[0]===id));
  if(group)return group.id;
  return contextualRoutes.find(item=>item.id===id)?.group||"";
}
export function labelFor(id:string):string {
  if(id==="overview")return "Home";
  for(const group of navGroups){
    const item=group.items.find(row=>row[0]===id);
    if(item)return item[1];
  }
  return contextualRoutes.find(item=>item.id===id)?.label||"Unknown page";
}
export function navMatches(raw:string,role:string){
  const query=raw.trim().toLowerCase();
  if(!query)return [];
  const routes=[
    {id:"overview",label:"Home",group:"",description:pageDescriptions.overview},
    ...navGroups.flatMap(group=>group.items.map(([id,label])=>({id,label,group:group.id,description:pageDescriptions[id]||group.description}))),
    ...contextualRoutes.map(item=>({...item})),
  ];
  return routes.filter(route=>visibleRoute(route.id,role) &&
    [route.label,route.description,route.id,...(oldAliases[route.id]||[])].some(text=>text.toLowerCase().includes(query))
  ).slice(0,12);
}
