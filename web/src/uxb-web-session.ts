/** R2.2/M2 — Web actor/CSRF admission for Core-authenticated responses.
 * Core alone authenticates the HttpOnly cookie, authorizes writes and binds
 * CSRF. The Web must not promote a malformed 200 body into an active role or
 * store arbitrary nested Core session values in React state.
 *
 * All three callers (login, MFA completion and GET /session after reload)
 * receive the same Core WebPrincipal shape. Session IDs are generated as
 * ws_<24 lowercase hex>, operator IDs as wop_<24 lowercase hex>, and the
 * server-derived CSRF is a 64-hex HMAC digest. No tokens are persisted.
 */
export type ObservedAuthenticatedWebSession={
  operator:{id:string,username:string,role:"Admin"|"Operator"|"Read Only"},
  csrf_token:string
};
const OPERATOR_ID=/^wop_[0-9a-f]{24}$/;
const SESSION_ID=/^ws_[0-9a-f]{24}$/;
const USERNAME=/^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const CSRF=/^[a-f0-9]{64}$/;
export function observedAuthenticatedWebSession(input:unknown):ObservedAuthenticatedWebSession|null{
  if(input===null||typeof input!=="object"||Array.isArray(input))return null;
  const payload=input as Record<string,unknown>;
  if(typeof payload.session_id!=="string"||!SESSION_ID.test(payload.session_id)
    ||typeof payload.csrf_token!=="string"||!CSRF.test(payload.csrf_token)
    ||payload.mfa_setup_required===true)return null;
  const operator=payload.operator;
  if(operator===null||typeof operator!=="object"||Array.isArray(operator))return null;
  const actor=operator as Record<string,unknown>;
  if(typeof actor.id!=="string"||!OPERATOR_ID.test(actor.id)
    ||typeof actor.username!=="string"||!USERNAME.test(actor.username)
    ||actor.role!=="Admin"&&actor.role!=="Operator"&&actor.role!=="Read Only")
    return null;
  // Copy only Core's expected display identity, not server/session metadata,
  // tokens, permissions, password/MFA fields or forged extra role claims.
  return {operator:{id:actor.id,username:actor.username,role:actor.role},
    csrf_token:payload.csrf_token};
}
