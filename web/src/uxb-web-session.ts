import {isObservedAbsoluteTime} from "./uxb-integrations-state";

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
type ObservedWebActor={id:string,username:string,role:"Admin"|"Operator"|"Read Only"};
export type ObservedAuthenticatedWebSession={
  operator:ObservedWebActor,csrf_token:string
};
const OPERATOR_ID=/^wop_[0-9a-f]{24}$/;
const SESSION_ID=/^ws_[0-9a-f]{24}$/;
const USERNAME=/^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const CSRF=/^[a-f0-9]{64}$/;
function observedWebActor(value:unknown):ObservedWebActor|null{
  if(value===null||typeof value!=="object"||Array.isArray(value))return null;
  const actor=value as Record<string,unknown>;
  if(typeof actor.id!=="string"||!OPERATOR_ID.test(actor.id)
    ||typeof actor.username!=="string"||!USERNAME.test(actor.username)
    ||actor.role!=="Admin"&&actor.role!=="Operator"&&actor.role!=="Read Only")
    return null;
  return {id:actor.id,username:actor.username,role:actor.role};
}
export function observedAuthenticatedWebSession(input:unknown):ObservedAuthenticatedWebSession|null{
  if(input===null||typeof input!=="object"||Array.isArray(input))return null;
  const payload=input as Record<string,unknown>;
  if(typeof payload.session_id!=="string"||!SESSION_ID.test(payload.session_id)
    ||typeof payload.csrf_token!=="string"||!CSRF.test(payload.csrf_token)
    ||payload.mfa_setup_required===true)return null;
  const operator=observedWebActor(payload.operator);
  if(!operator)return null;
  // Copy only Core's expected display identity, not server/session metadata,
  // tokens, permissions, password/MFA fields or forged extra role claims.
  return {operator,csrf_token:payload.csrf_token};
}

/** The initial MFA enrollment is a PRE-SESSION Core challenge, not a
 * logged-in operator. Bind its QR to the server's exact 6-digit/30s
 * TOTP issuer, username and generated secret; never render arbitrary URI. */
export type ObservedWebMfaChallenge={
  mfa_setup_required:true,enrollment_token:string,totp_secret:string,
  otpauth_uri:string,expires_at:string,operator:ObservedWebActor
};
const ENROLLMENT=/^[A-Za-z0-9_-]{43}$/;
const TOTP_SECRET=/^[A-Z2-7]{32}$/;
export function observedWebMfaChallenge(input:unknown):ObservedWebMfaChallenge|null{
  if(input===null||typeof input!=="object"||Array.isArray(input))return null;
  const value=input as Record<string,unknown>,operator=observedWebActor(value.operator);
  if(value.mfa_setup_required!==true||!operator
    ||typeof value.enrollment_token!=="string"||!ENROLLMENT.test(value.enrollment_token)
    ||typeof value.totp_secret!=="string"||!TOTP_SECRET.test(value.totp_secret)
    ||typeof value.otpauth_uri!=="string"
    ||!isObservedAbsoluteTime(value.expires_at))return null;
  const canonicalUri="otpauth://totp/"+encodeURIComponent("Data Relay Link:"+operator.username)
    +"?secret="+value.totp_secret+"&issuer=Data%20Relay%20Link&digits=6&period=30";
  if(value.otpauth_uri!==canonicalUri)return null;
  return {mfa_setup_required:true,enrollment_token:value.enrollment_token,
    totp_secret:value.totp_secret,otpauth_uri:value.otpauth_uri,
    expires_at:value.expires_at,operator};
}

/** Core issues ten one-time 4-4-4-4 recovery codes AFTER successfully
 * enrolling MFA. Do not claim completion or lose the one-time display on
 * a malformed 200, mixed fields or unverified authenticated Web session. */
const RECOVERY=/^[A-HJ-NP-Z2-9]{4}(?:-[A-HJ-NP-Z2-9]{4}){3}$/;
export function observedWebMfaCompletion(input:unknown):{
  session:ObservedAuthenticatedWebSession,recovery_codes:string[]
}|null{
  const session=observedAuthenticatedWebSession(input);
  if(!session||input===null||typeof input!=="object"||Array.isArray(input))return null;
  const codes=(input as Record<string,unknown>).recovery_codes;
  if(!Array.isArray(codes)||codes.length!==10
    ||codes.some(code=>typeof code!=="string"||!RECOVERY.test(code))
    ||new Set(codes).size!==10)return null;
  return {session,recovery_codes:[...codes]};
}
