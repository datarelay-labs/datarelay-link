import {createStandardAdministrationTasks} from "@datarelay-labs/foundation";

/**
 * Product-owned PF-5B Administration capability projection.
 *
 * These labels/groups come from the pinned Foundation vocabulary; only Link
 * supplies availability, actor access and destinations. Web/Core authorization
 * remains the final enforcement point.
 */
export function createLinkFoundationAdministrationTasks(role:string){
  const admin=role==="Admin";
  // Only recognized, authenticated Link Web roles may see management read
  // surfaces. Unknown/unset role strings cannot inherit implicit View access.
  const authenticated=admin||role==="Operator"||role==="Read Only";
  const readAccess=authenticated?"view":"none";
  const unavailable={availability:"unavailable",access:"view"} as const;
  return createStandardAdministrationTasks({
    "core.https":{
      // The standard task includes Web listener/redirect configuration, which
      // Link does not implement. This only links to MCP TLS certificate status.
      availability:"read_only",
      access:readAccess,
      notes:"MCP TLS certificate status only. Shared Web HTTPS listener and redirect configuration is not available in Link.",
      ...(authenticated?{target:{kind:"action" as const,actionId:"link.certificate"}}:{})
    },
    "core.users":{
      // Supported on this product, but only Admin can see/manage Web users.
      // The actor filter must never claim the underlying feature is missing.
      availability:"supported",
      access:admin?"manage":"none",
      ...(admin?{target:{kind:"action" as const,actionId:"link.users"}}:{})
    },
    "core.password":unavailable,
    "core.timezone":unavailable,
    "core.network":unavailable,
    "core.retention":unavailable,
    "core.backup-import":{
      // Link provides Core-owned backup validation, not the generic shared
      // configuration import editor. A restore remains Admin-only, separately
      // confirmed and authorized by Core; this shortcut never enables it.
      availability:"read_only",
      access:readAccess,
      notes:"Native backup archive validation only; generic configuration import is unavailable. Restore requires separate Admin authorization and confirmation.",
      ...(authenticated?{target:{kind:"action" as const,actionId:"link.backup"}}:{})
    },
    "core.audit":{
      availability:"read_only",access:readAccess,
      ...(authenticated?{target:{kind:"action" as const,actionId:"link.audit"}}:{})
    },
    "core.health":{
      availability:"read_only",access:readAccess,
      ...(authenticated?{target:{kind:"action" as const,actionId:"link.health"}}:{})
    }
  });
}
