#!/usr/bin/env python3
"""Approved UI06 two-person Temporary Access request authority."""
from __future__ import annotations

import base64, json, re, secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from drlink_control_db import ControlPlaneError
from drlink_control_plane import ConcurrencyError
from drlink_management_change import ManagementChangeService
from drlink_v30_temporal import canonical_expiry

REVIEW_PERMISSION="management-access-request-review"
REQUEST_PERMISSION="management-temporary-access"
MIN_DURATION_SECONDS=300
MAX_DURATION_SECONDS=86400
_ALLOWED_PLANES=frozenset({"remote","internet","ai"})
_ALLOWED_STATES=frozenset({"PENDING","APPROVED","REJECTED","EXPIRED","REVOKED"})
_ID_RE=re.compile(r"^tar_[A-Za-z0-9_-]{16,96}$")
_FORBIDDEN_TEXT_RE=re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")

def _utc_now(): return datetime.now(timezone.utc)
def _utc_text(value): return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def _parse_utc(value):
    text=str(value or "").strip()
    if text.endswith("Z"): text=text[:-1]+"+00:00"
    parsed=datetime.fromisoformat(text)
    if parsed.tzinfo is None: raise ValueError("timestamp requires timezone")
    return parsed.astimezone(timezone.utc)

def _permission_set(values:Iterable[str])->frozenset[str]:
    return frozenset(str(v or "").strip().lower() for v in values if str(v or "").strip())

def _safe_text(value:Any,*,label:str,minimum:int=0,maximum:int=500)->str:
    if not isinstance(value,str): raise ControlPlaneError(label+" must be text.")
    text=value.strip()
    if len(text)<minimum or len(text)>maximum or _FORBIDDEN_TEXT_RE.search(text):
        raise ControlPlaneError(label+" is invalid or outside the supported length.")
    return text

def _duration(value:Any,*,label:str="Temporary Access duration")->int:
    if isinstance(value,bool) or not isinstance(value,int):
        raise ControlPlaneError(label+" must be an integer number of seconds.")
    if value<MIN_DURATION_SECONDS or value>MAX_DURATION_SECONDS:
        raise ControlPlaneError(f"{label} must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS} seconds.")
    return value

def _request_id(value:Any)->str:
    text=str(value or "").strip()
    if not _ID_RE.fullmatch(text): raise ControlPlaneError("Temporary Access request was not found.")
    return text

def _encode_cursor(created_at:str,request_id:str)->str:
    raw=json.dumps([created_at,request_id],separators=(",",":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def _decode_cursor(value:Optional[str])->Optional[tuple[str,str]]:
    text=str(value or "").strip()
    if not text: return None
    if len(text)>512: raise ControlPlaneError("Temporary Access request cursor is invalid.")
    try:
        pad="="*((4-len(text)%4)%4)
        payload=json.loads(base64.urlsafe_b64decode((text+pad).encode()))
    except Exception as exc:
        raise ControlPlaneError("Temporary Access request cursor is invalid.") from exc
    if not isinstance(payload,list) or len(payload)!=2 or not all(isinstance(x,str) for x in payload):
        raise ControlPlaneError("Temporary Access request cursor is invalid.")
    if len(payload[0])>64 or not _ID_RE.fullmatch(payload[1]):
        raise ControlPlaneError("Temporary Access request cursor is invalid.")
    try: _parse_utc(payload[0])
    except ValueError as exc: raise ControlPlaneError("Temporary Access request cursor is invalid.") from exc
    return payload[0],payload[1]

class TemporaryAccessRequestService:
    def __init__(self,root:Optional[str]=None):
        self.root=root
        self.change=ManagementChangeService(root)
        self.plane=self.change.plane
        self.server_id=self.change.server_id
    def close(self): self.change.close()
    def __enter__(self): return self
    def __exit__(self,exc_type,exc,tb): self.close()

    @staticmethod
    def _require_requester(role,permissions):
        if str(role or "").strip() not in {"Admin","Operator"}:
            raise ControlPlaneError("Admin or Operator role is required for Temporary Access requests.")
        if REQUEST_PERMISSION not in _permission_set(permissions):
            raise ControlPlaneError("Temporary Access request permission is required.")

    @staticmethod
    def _require_reviewer(role,permissions):
        if str(role or "").strip()!="Admin":
            raise ControlPlaneError("Admin role is required to review Temporary Access requests.")
        if REVIEW_PERMISSION not in _permission_set(permissions):
            raise ControlPlaneError("Temporary Access review permission is required.")
    def _resolve_rule(self,plane,rule):
        import drlink_v24 as v24
        family=str(plane or "").strip().lower()
        if family not in _ALLOWED_PLANES: raise ControlPlaneError("Unsupported access plane.")
        if str(v24.get_access_policy(self.plane,family).get("mode") or "").lower()!="whitelist":
            raise ControlPlaneError("Temporary Access requests require a WHITELIST policy.")
        name=str(rule or "").strip()
        if not name: raise ControlPlaneError("Temporary Access rule is required.")
        row=(self.plane.conn.execute("SELECT * FROM ai_policy_rules WHERE name=? COLLATE NOCASE",(name,)).fetchone()
             if family=="ai" else self.plane._get_rule(family,name))
        if not row: raise ControlPlaneError("Temporary Access rule was not found.")
        canonical=str(row["name"])
        expiry=str(row["expires_at"]).strip() if "expires_at" in row.keys() and row["expires_at"] else None
        return family,canonical,f"{family}-access-rule",expiry

    def _read_row(self,request_id):
        row=self.plane.conn.execute("SELECT * FROM temporary_access_requests WHERE id=?",(_request_id(request_id),)).fetchone()
        if not row: raise ControlPlaneError("Temporary Access request was not found.")
        return row

    def _visible(self,row,*,actor_id,role,permissions):
        actor=str(actor_id or "").strip(); perms=_permission_set(permissions)
        if str(row["requester_actor_id"])==actor and REQUEST_PERMISSION in perms: return
        if str(role or "").strip()=="Admin" and REVIEW_PERMISSION in perms: return
        raise ControlPlaneError("Temporary Access request was not found.")

    def _project(self,row,*,now=None):
        current=now or _utc_now(); status=str(row["status"])
        expiry=str(row["approved_expires_at"] or "").strip() or None
        if status=="APPROVED" and expiry:
            try:
                if current>=_parse_utc(expiry): status="EXPIRED"
            except ValueError: status="EXPIRED"
        if status not in _ALLOWED_STATES: raise ControlPlaneError("Temporary Access request state is invalid.")
        return {
            "id":str(row["id"]),"server_id":str(row["server_id"]),
            "requester_actor_id":str(row["requester_actor_id"]),"requester_role":str(row["requester_role"]),
            "plane":str(row["plane"]),"resource_type":str(row["resource_type"]),"resource_ref":str(row["resource_ref"]),
            "purpose":str(row["purpose"]),"requested_duration_seconds":int(row["requested_duration_seconds"]),
            "approved_duration_seconds":int(row["approved_duration_seconds"]) if row["approved_duration_seconds"] is not None else None,
            "requested_revision":int(row["requested_revision"]),"status":status,"created_at":str(row["created_at"]),
            "reviewed_at":str(row["reviewed_at"] or "") or None,"reviewer_actor_id":str(row["reviewer_actor_id"] or "") or None,
            "decision_reason":str(row["decision_reason"] or ""),"approved_expires_at":expiry,
            "applied_revision":int(row["applied_revision"]) if row["applied_revision"] is not None else None,
            "revoked_at":str(row["revoked_at"] or "") or None,"revoked_by_actor_id":str(row["revoked_by_actor_id"] or "") or None,
            "revoked_revision":int(row["revoked_revision"]) if row["revoked_revision"] is not None else None,
            "row_version":int(row["row_version"]),
        }

    def create(self,*,actor_id,role,permissions,plane,rule,purpose,duration_seconds,now=None):
        self._require_requester(role,permissions)
        actor=_safe_text(str(actor_id or ""),label="Requester actor",minimum=1,maximum=256)
        why=_safe_text(purpose,label="Purpose",minimum=1,maximum=500)
        duration=_duration(duration_seconds); current=now or _utc_now()
        request_id="tar_"+secrets.token_urlsafe(18)
        self.plane.conn.execute("BEGIN IMMEDIATE")
        try:
            family,name,resource_type,_=self._resolve_rule(plane,rule)
            revision=self.plane.current_revision()
            if self.plane.conn.execute(
                "SELECT id FROM temporary_access_requests WHERE requester_actor_id=? AND plane=? AND resource_type=? AND resource_ref=? AND status='PENDING' LIMIT 1",
                (actor,family,resource_type,name)).fetchone():
                raise ControlPlaneError("A pending Temporary Access request already exists for this requester and rule.")
            self.plane.conn.execute(
                "INSERT INTO temporary_access_requests(id,server_id,requester_actor_id,requester_role,plane,resource_type,resource_ref,purpose,requested_duration_seconds,requested_revision,status,created_at,row_version) VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?,1)",
                (request_id,self.server_id,actor,str(role),family,resource_type,name,why,duration,revision,_utc_text(current)))
            self.plane._audit(revision=0,action="temporary access request create",entity_type="temporary-access-request",
                entity_id=request_id,operation="temporary_access.request.created",
                after=json.dumps({"plane":family,"resource_type":resource_type,"resource_ref":name,
                    "requested_duration_seconds":duration,"requested_revision":revision},sort_keys=True,separators=(",",":")),
                actor=actor,interface="WEB")
            self.plane.conn.execute("COMMIT")
        except Exception:
            if self.plane.conn.in_transaction: self.plane.conn.execute("ROLLBACK")
            raise
        return self._project(self._read_row(request_id),now=current)
    def list(self,*,actor_id,role,permissions,status="",limit=50,cursor="",now=None):
        self._require_requester(role,permissions)
        actor=_safe_text(str(actor_id or ""),label="Actor",minimum=1,maximum=256)
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<1 or limit>100:
            raise ControlPlaneError("Temporary Access request limit must be 1..100.")
        requested=str(status or "").strip().upper()
        if requested and requested not in _ALLOWED_STATES:
            raise ControlPlaneError("Temporary Access request status filter is invalid.")
        after=_decode_cursor(cursor)
        reviewer=str(role or "").strip()=="Admin" and REVIEW_PERMISSION in _permission_set(permissions)
        where=["1=1"]; args=[]
        if not reviewer: where.append("requester_actor_id=?"); args.append(actor)
        current=now or _utc_now(); now_text=_utc_text(current)
        if requested=="EXPIRED":
            where+=["status='APPROVED'","approved_expires_at IS NOT NULL","approved_expires_at<=?"]; args.append(now_text)
        elif requested=="APPROVED":
            where+=["status='APPROVED'","approved_expires_at IS NOT NULL","approved_expires_at>?"]; args.append(now_text)
        elif requested: where.append("status=?"); args.append(requested)
        if after:
            where.append("(created_at<? OR (created_at=? AND id<?))"); args += [after[0],after[0],after[1]]
        rows=self.plane.conn.execute(
            "SELECT * FROM temporary_access_requests WHERE %s ORDER BY created_at DESC,id DESC LIMIT ?"%" AND ".join(where),
            tuple(args+[limit+1])).fetchall()
        items=[self._project(row,now=current) for row in rows[:limit]]
        return {"items":items,"next_cursor":_encode_cursor(items[-1]["created_at"],items[-1]["id"]) if len(rows)>limit and items else None,"limit":limit}

    def get(self,request_id,*,actor_id,role,permissions,now=None):
        row=self._read_row(request_id); self._visible(row,actor_id=actor_id,role=role,permissions=permissions)
        return self._project(row,now=now)

    @staticmethod
    def _policy_safety_ok(result):
        regression=dict(result.get("policy_regression") or {}); blast=dict(result.get("blast_radius") or {})
        if not bool(regression.get("ok")):
            raise ControlPlaneError("Required Policy Regression Tests failed. No changes were applied.")
        if bool(dict(blast.get("limits") or {}).get("truncated")):
            raise ControlPlaneError("Temporary Access impact is truncated. No changes were applied.")

    def _canonical_expiry_mutation(self,*,family,rule_name,expires_at,expected_revision):
        import drlink_v24 as v24
        prev=bool(getattr(self.plane,"_batch_mode",False)); n=len(getattr(self.plane,"_batch_results",[]))
        self.plane._batch_mode=True
        try:
            if family=="ai":
                return v24.set_ai_access_rule(self.plane,rule_name,expires_at=expires_at,oneshot=True,confirm=True,expected_revision=expected_revision)
            return v24.set_access_rule(self.plane,family,rule_name,expires_at=expires_at,oneshot=True,confirm=True,expected_revision=expected_revision)
        finally:
            self.plane._batch_mode=prev
            if hasattr(self.plane,"_batch_results"): del self.plane._batch_results[n:]

    def review(self,request_id,*,actor_id,role,permissions,decision,approved_duration_seconds,reason,row_version,now=None):
        self._require_reviewer(role,permissions)
        actor=_safe_text(str(actor_id or ""),label="Reviewer actor",minimum=1,maximum=256)
        ident=_request_id(request_id); choice=str(decision or "").strip().lower()
        if choice not in {"approve","reject"}: raise ControlPlaneError("Temporary Access review decision must be approve or reject.")
        if isinstance(row_version,bool) or not isinstance(row_version,int) or row_version<1:
            raise ControlPlaneError("Temporary Access request row version is invalid.")
        note=_safe_text(str(reason or ""),label="Decision reason",minimum=0,maximum=500); current=now or _utc_now()
        first=self._read_row(ident)
        if str(first["requester_actor_id"])==actor: raise ControlPlaneError("Requester and reviewer must be different actors.")
        if str(first["server_id"])!=self.server_id: raise ControlPlaneError("Temporary Access request was not found.")
        if str(first["status"])!="PENDING" or int(first["row_version"])!=row_version:
            raise ControlPlaneError("Temporary Access request is no longer pending at this version.")
        if choice=="reject":
            self.plane.conn.execute("BEGIN IMMEDIATE")
            try:
                row=self._read_row(ident)
                if (str(row["status"])!="PENDING" or int(row["row_version"])!=row_version
                    or str(row["requester_actor_id"])==actor or str(row["server_id"])!=self.server_id):
                    raise ControlPlaneError("Temporary Access request changed before review.")
                requested_revision=int(row["requested_revision"])
                current_revision=self.plane.current_revision()
                if current_revision!=requested_revision:
                    raise ConcurrencyError(
                        f"REVISION_CONFLICT\nTemporary Access request was prepared at revision {requested_revision} "
                        f"but current revision is {current_revision}.\nNo changes were applied. Create a fresh request."
                    )
                family=str(row["plane"]); rule_name=str(row["resource_ref"]); resource_type=str(row["resource_type"])
                rf,rn,rt,_=self._resolve_rule(family,rule_name)
                if rf!=family or rn!=rule_name or rt!=resource_type:
                    raise ControlPlaneError("Temporary Access target changed before review.")
                updated=self.plane.conn.execute(
                    "UPDATE temporary_access_requests SET status='REJECTED',reviewed_at=?,reviewer_actor_id=?,decision_reason=?,row_version=row_version+1 WHERE id=? AND status='PENDING' AND row_version=?",
                    (_utc_text(current),actor,note,ident,row_version))
                if updated.rowcount!=1: raise ControlPlaneError("Temporary Access request changed before review.")
                self.plane._audit(revision=0,action="temporary access request reject",entity_type="temporary-access-request",
                    entity_id=ident,operation="temporary_access.request.rejected",
                    after=json.dumps({"requester_actor_id":str(row["requester_actor_id"]),"reviewer_actor_id":actor,
                        "plane":str(row["plane"]),"resource_type":str(row["resource_type"]),"resource_ref":str(row["resource_ref"])},
                        sort_keys=True,separators=(",",":")),actor=actor,interface="WEB")
                self.plane.conn.execute("COMMIT")
            except Exception:
                if self.plane.conn.in_transaction: self.plane.conn.execute("ROLLBACK")
                raise
            return self._project(self._read_row(ident),now=current)
        requested_duration=int(first["requested_duration_seconds"])
        approved=requested_duration if approved_duration_seconds is None else _duration(approved_duration_seconds,label="Approved Temporary Access duration")
        if approved>requested_duration: raise ControlPlaneError("Reviewer cannot extend the requested Temporary Access duration.")
        requested_revision=int(first["requested_revision"])
        if self.plane.current_revision()!=requested_revision:
            raise ConcurrencyError(f"REVISION_CONFLICT\nTemporary Access request was prepared at revision {requested_revision} but current revision is {self.plane.current_revision()}.\nNo changes were applied. Create a fresh request.")
        desired=canonical_expiry(_utc_text(current+timedelta(seconds=approved)))
        family=str(first["plane"]); rule_name=str(first["resource_ref"])
        from drlink_policy_safety import preview_rule_expiry_policy_safety
        preflight=preview_rule_expiry_policy_safety(self.plane,family=family,rule_name=rule_name,expires_at=desired)
        self._policy_safety_ok(preflight)
        impact={"request_id":ident,"requester_actor_id":str(first["requester_actor_id"]),"reviewer_actor_id":actor,
            "plane":family,"resource_type":str(first["resource_type"]),"resource_ref":rule_name,
            "requested_duration_seconds":requested_duration,"approved_duration_seconds":approved,
            "approved_expires_at":desired,"requires_confirmation":True,"access_broadened":True}
        def writer():
            row=self._read_row(ident)
            if str(row["status"])!="PENDING" or int(row["row_version"])!=row_version or str(row["requester_actor_id"])==actor or int(row["requested_revision"])!=requested_revision:
                raise ControlPlaneError("Temporary Access request changed before review.")
            rf,rn,rt,_=self._resolve_rule(str(row["plane"]),str(row["resource_ref"]))
            if rf!=family or rn!=rule_name or rt!=str(row["resource_type"]):
                raise ControlPlaneError("Temporary Access target changed before review.")
            safety=preview_rule_expiry_policy_safety(self.plane,family=family,rule_name=rule_name,expires_at=desired)
            self._policy_safety_ok(safety)
            self._canonical_expiry_mutation(family=family,rule_name=rule_name,expires_at=desired,expected_revision=requested_revision)
            next_revision=requested_revision+1
            updated=self.plane.conn.execute(
                "UPDATE temporary_access_requests SET status='APPROVED',reviewed_at=?,reviewer_actor_id=?,decision_reason=?,approved_duration_seconds=?,approved_expires_at=?,applied_revision=?,row_version=row_version+1 WHERE id=? AND status='PENDING' AND row_version=?",
                (_utc_text(current),actor,note,approved,desired,next_revision,ident,row_version))
            if updated.rowcount!=1: raise ControlPlaneError("Temporary Access request changed before review.")
            out=self._project(self._read_row(ident),now=current)
            out.update({"entity":{"type":"temporary-access-request","id":ident},"operation":"temporary_access.request.approved","after":"approved until "+desired})
            return out
        return self.plane._mutate("approve temporary access request "+ident,"approve two-person Temporary Access request",
            writer,expected_revision=requested_revision,impact=impact,confirm=True,actor=actor,interface="WEB")

    def revoke(self,request_id,*,actor_id,role,permissions,row_version,now=None):
        self._require_requester(role,permissions)
        actor=_safe_text(str(actor_id or ""),label="Actor",minimum=1,maximum=256)
        ident=_request_id(request_id)
        if isinstance(row_version,bool) or not isinstance(row_version,int) or row_version<1:
            raise ControlPlaneError("Temporary Access request row version is invalid.")
        current=now or _utc_now(); first=self._read_row(ident)
        admin=str(role or "").strip()=="Admin" and REVIEW_PERMISSION in _permission_set(permissions)
        if str(first["requester_actor_id"])!=actor and not admin:
            raise ControlPlaneError("Temporary Access revoke is not authorized.")
        visible=self._project(first,now=current)
        if visible["status"]!="APPROVED" or int(first["row_version"])!=row_version:
            raise ControlPlaneError("Temporary Access request is not an active approved request.")
        approved_expiry=str(first["approved_expires_at"] or "").strip()
        family=str(first["plane"]); rule_name=str(first["resource_ref"]); current_revision=self.plane.current_revision()
        revoke_expiry=canonical_expiry(_utc_text(current))
        from drlink_policy_safety import preview_rule_expiry_policy_safety
        preflight=preview_rule_expiry_policy_safety(self.plane,family=family,rule_name=rule_name,expires_at=revoke_expiry)
        self._policy_safety_ok(preflight)
        impact={"request_id":ident,"requester_actor_id":str(first["requester_actor_id"]),"revoked_by_actor_id":actor,
            "plane":family,"resource_type":str(first["resource_type"]),"resource_ref":rule_name,
            "previous_expires_at":approved_expiry,"revoked_at":revoke_expiry,"requires_confirmation":True,"access_narrowed":True}
        def writer():
            row=self._read_row(ident)
            if int(row["row_version"])!=row_version or self._project(row,now=current)["status"]!="APPROVED":
                raise ControlPlaneError("Temporary Access request changed before revoke.")
            if str(row["requester_actor_id"])!=actor and not admin:
                raise ControlPlaneError("Temporary Access revoke is not authorized.")
            rf,rn,rt,current_expiry=self._resolve_rule(str(row["plane"]),str(row["resource_ref"]))
            if rf!=family or rn!=rule_name or rt!=str(row["resource_type"]) or current_expiry!=approved_expiry:
                raise ControlPlaneError("Temporary Access rule no longer matches the approved request.")
            safety=preview_rule_expiry_policy_safety(self.plane,family=family,rule_name=rule_name,expires_at=revoke_expiry)
            self._policy_safety_ok(safety)
            self._canonical_expiry_mutation(family=family,rule_name=rule_name,expires_at=revoke_expiry,expected_revision=current_revision)
            next_revision=current_revision+1
            updated=self.plane.conn.execute(
                "UPDATE temporary_access_requests SET status='REVOKED',revoked_at=?,revoked_by_actor_id=?,revoked_revision=?,row_version=row_version+1 WHERE id=? AND status='APPROVED' AND row_version=?",
                (_utc_text(current),actor,next_revision,ident,row_version))
            if updated.rowcount!=1: raise ControlPlaneError("Temporary Access request changed before revoke.")
            out=self._project(self._read_row(ident),now=current)
            out.update({"entity":{"type":"temporary-access-request","id":ident},"operation":"temporary_access.request.revoked","after":"revoked at "+revoke_expiry})
            return out
        return self.plane._mutate("revoke temporary access request "+ident,"revoke approved two-person Temporary Access request",
            writer,expected_revision=current_revision,impact=impact,confirm=True,actor=actor,interface="WEB")
