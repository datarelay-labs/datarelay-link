#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
ADMIN_SOURCE = (ROOT / "web/src/foundation-administration.ts").read_text(encoding="utf-8")
P0_ACCESS_SOURCE = (ROOT / "web/src/p0-access-policy.tsx").read_text(encoding="utf-8")
P0_ENROLL_SOURCE = (ROOT / "web/src/p0-enrollment.tsx").read_text(encoding="utf-8")
NAV_SOURCE = (ROOT / "web/src/uxb-navigation.ts").read_text(encoding="utf-8")
HOME_SOURCE = (ROOT / "web/src/uxb-home.tsx").read_text(encoding="utf-8")
SETUP_SOURCE = (ROOT / "web/src/uxb-setup.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web/dist/styles.css").read_text(encoding="utf-8")
PACKAGE = (ROOT / "web/package.json").read_text(encoding="utf-8")
PACKAGE_LOCK = (ROOT / "web/package-lock.json").read_text(encoding="utf-8")
UX = (ROOT / "docs/WEB_SAAS_UX_SYSTEM.md").read_text(encoding="utf-8")


class V30WebSaasUxContractTests(unittest.TestCase):
    def test_dr_control_semantic_token_parity_is_frozen(self):
        required = {
            "--dr-font-family-ui": 'Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
            "--dr-layout-sidebar-expanded": "260px",
            "--dr-layout-sidebar-collapsed": "57px",
            "--dr-layout-content-max": "1440px",
            "--dr-radius-control": "8px",
            "--dr-radius-card": "8px",
            "--dr-brand-mark": "#00d084",
            "--dr-brand-relay": "#007e4f",
            "--dr-surface-page": "oklch(98.75% 0 0)",
            "--dr-surface-panel": "#fff",
            "--dr-action-primary": "oklch(54.6% .245 262.881)",
            "--dr-status-success": "#047857",
            "--dr-status-warning": "#92400e",
            "--dr-status-critical": "#b42318",
            "--dr-focus-ring": "#1473e6",
        }
        compact = CSS.replace(" ", "")
        for key, value in required.items():
            self.assertIn("%s:%s" % (key, value.replace(" ", "")), compact)
        for dark in (
            "--dr-surface-page:oklch(10% 0 0)",
            "--dr-surface-panel:oklch(17% 0 0)",
            "--dr-status-success:#34d399",
            "--dr-status-warning:#f59e0b",
            "--dr-status-critical:#f87171",
        ):
            self.assertIn(dark.replace(" ", ""), compact)
        for global_marker in (
            "text-rendering:optimizeLegibility",
            "scrollbar-width:thin",
            "::selection",
            "box-shadow:0 1px 2px rgba(0,0,0,.05)",
        ):
            self.assertIn(global_marker, CSS)

    def test_navigation_is_bounded_and_utilities_are_contextual(self):
        block = re.search(r"export const navGroups = \[(.*?)\] as const;", NAV_SOURCE, re.S)
        self.assertIsNotNone(block)
        text = block.group(1)
        groups = re.findall(r'id:"([^"]+)",label:"([^"]+)"', text)
        self.assertEqual(
            groups,
            [
                ("connections", "Connections"),
                ("access", "Access"),
                ("activity", "Activity & Health"),
                ("administration", "Administration"),
            ],
        )
        self.assertIn('if(id==="overview")return "Home"', NAV_SOURCE)
        for utility in ('["search","Search"]', '["doctor","Doctor"]', '["enrollments","Connect Agent"]', '["drafts","Draft Workspace"]'):
            self.assertNotIn(utility, text)
        self.assertIn('["views","Saved Views"]', text)
        self.assertNotIn('{id:"views",label:"Saved views",group:"activity"', NAV_SOURCE)
        for contextual in (
            'Search hosts, services, policies, identities',
            'Saved Views', 'Set up a connection', 'Troubleshoot',
        ):
            self.assertIn(contextual, SOURCE + NAV_SOURCE)
        self.assertIn('const group=groupFor(id)', SOURCE)
        self.assertIn('navMatches(query,operator.role)', SOURCE)
        self.assertIn('pageDescriptions[active]', SOURCE)
        self.assertIn('aria-label="Breadcrumb"', SOURCE)

    def test_every_web_ui_api_path_has_a_server_route(self):
        # Catch source-level UI/backend drift before packaging: every
        # literal Web fetch prefix must be dispatched by the same repo's
        # Web server, including its pre-session auth routes.
        ui = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "web/src").glob("*"))
            if path.suffix in (".tsx", ".ts")
        )
        server = (ROOT / "lib/drlink_web_service.py").read_text(encoding="utf-8")
        requested = set(re.findall(r'"(/api/v1/[a-z0-9/_-]+)', ui))
        exact = set(
            re.findall(r'if (?:path|parsed\.path) == "(/api/v1/[a-z0-9/_-]+)"', server)
        )
        prefix = set(
            re.findall(r'if (?:path|parsed\.path)\.startswith\("(/api/v1/[a-z0-9/_-]+)"\)', server)
        )
        missing = sorted(
            route for route in requested
            if route not in exact and not any(route.startswith(p) for p in prefix)
        )
        self.assertGreaterEqual(len(requested), 60)
        self.assertFalse(missing, missing)

    def test_web_api_refresh_bootstraps_csrf_before_core_mutations(self):
        # An HttpOnly session cookie survives a tab refresh, but JS state
        # does not. A GET session bootstrap must restore CSRF in memory.
        self.assertIn('api("/api/v1/session").then(d=>{', SOURCE)
        self.assertIn('csrf=d.csrf_token;', SOURCE)
        self.assertIn('if(csrf)headers["X-CSRF-Token"]=csrf;', SOURCE)
        self.assertNotIn('localStorage.setItem("csrf', SOURCE)
        self.assertNotIn('sessionStorage', SOURCE)

    def test_draft_edit_and_failed_validation_invalidate_stale_apply(self):
        # UXE-11 supplemental source guard: UI must retire an old Core plan
        # as soon as the edited bundle or exported editor content changes.
        draft = SOURCE.split("function DraftWorkspace(){", 1)[1].split(
            "function BlastRadiusView(", 1
        )[0]
        self.assertIn("function changeBundle(value:string){", draft)
        self.assertIn("setBundle(value);setPreview(null);setTestResult(null);setConfirmation(\"\");", draft)
        self.assertIn("onChange={e=>changeBundle(e.target.value)}", draft)
        self.assertIn('setPreview(null);setConfirmation("");', draft)
        self.assertIn('const planEpoch=useRef(0);', draft)
        self.assertIn('planEpoch.current+=1;', draft)
        self.assertIn('const epoch=++planEpoch.current;', draft)
        self.assertIn('if(epoch!==planEpoch.current)return;', draft)
        self.assertIn('if(!draftId||!preview?.change_plan_id||confirmation!=="APPLY")return;', draft)
        self.assertNotIn("const id=await ensureDraft();\n      const result=await api(\"/api/v1/drafts/\"+id+\"/apply\"", draft)

    def test_guided_forms_invalidate_preview_on_changed_inputs(self):
        # UXE-11: a previously reviewed change plan must not remain
        # actionable after editing its host/object/policy input fields.
        for form in (
            'key={JSON.stringify([host,label,description,tags])}',
            'key={JSON.stringify([kind,operation,name,value,subtype,port,items])}',
            'key={JSON.stringify([plane,operation,enabled])}',
        ):
            self.assertIn(form, SOURCE)
        lifecycle = SOURCE.split('function ManagedHostLifecyclePanel(){', 1)[1].split(
            'function GuidedObjectPanel(){', 1
        )[0]
        self.assertIn('onChange={e=>{setHost(e.target.value);setPreview(null);setConfirmation("")}}', lifecycle)

    def test_remaining_security_workflows_retire_stale_previews(self):
        # UXE-11 supplementary checks for rarely used Core-backed changes.
        temporary = SOURCE.split('function TemporaryAccessPanel(){', 1)[1].split(
            'function PolicySafetyPanel(', 1
        )[0]
        self.assertIn('function resetChangePlan(){', temporary)
        for field in ('plane', 'rule', 'operation', 'expiresAt'):
            self.assertIn('resetChangePlan();set' + field[0].upper() + field[1:] + '(e.target.value)', temporary)
        safety = SOURCE.split('function PolicySafetyPanel(', 1)[1].split(
            'function LinkFoundationAdministration(', 1
        )[0]
        self.assertIn('function invalidateTestPreview(){', safety)
        for field in ('testName', 'expected'):
            self.assertIn('invalidateTestPreview();set' + field[0].upper() + field[1:] + '(e.target.value)', safety)
        for field in ('required', 'enabled'):
            self.assertIn('invalidateTestPreview();set' + field[0].upper() + field[1:] + '(e.target.checked)', safety)
        operations = SOURCE.split('function AccessOperations(', 1)[1].split(
            'function AuditExplorer(', 1
        )[0]
        self.assertIn('function invalidateCutoff(){', operations)
        self.assertIn('function changeDiagnosisFlow(', operations)

    def test_uxb_home_and_health_do_not_misreport_missing_evidence_as_empty(self):
        self.assertIn('setActivity(observedRecentFeed(auditResult))', SOURCE)
        self.assertIn('setChanges(observedRecentFeed(revisionResult))', SOURCE)
        self.assertIn('activity.status!=="ready"', SOURCE)
        self.assertIn('changes.status!=="ready"', SOURCE)
        self.assertIn('UNKNOWN · Recent Activity unavailable', SOURCE)
        self.assertIn('UNKNOWN · Change History unavailable', SOURCE)
        self.assertIn('const coreStatus=coreHealthState(data)', SOURCE)
        self.assertIn('const configuredPlanes=accessPlaneCount(data)', SOURCE)
        self.assertIn('configuredPlanes===null?"UNKNOWN"', SOURCE)
        self.assertIn('observedNumber(jobs.active_jobs)', SOURCE)
        self.assertNotIn('Remote, Internet and AI configured', SOURCE)
        self.assertIn('String(value??"UNKNOWN")', SOURCE)

    def test_global_search_cannot_show_stale_core_resources(self):
        search = SOURCE.split("function GlobalSearch(", 1)[1].split(
            "function Shell(", 1
        )[0]
        self.assertIn("const requestGeneration=useRef(0);", search)
        self.assertIn("function changeQuery(value:string){", search)
        self.assertIn("requestGeneration.current+=1;", search)
        self.assertIn('onChange={e=>changeQuery(e.target.value)}', search)
        self.assertIn("const generation=++requestGeneration.current;", search)
        self.assertIn("if(requestGeneration.current!==generation)return;", search)
        self.assertIn('if(!Array.isArray(data?.items))throw new Error(', search)

    def test_core_access_evidence_matches_current_flow_and_blocks_stale_response(self):
        access=P0_ACCESS_SOURCE
        operations=SOURCE.split('function AccessOperations(', 1)[1].split('function AuditExplorer(', 1)[0]
        self.assertIn("export function coreFlowKey(", access)
        self.assertIn("export function visibleCoreEvidence(", access)
        self.assertIn("const currentTraceKey=coreFlowKey(", access)
        self.assertIn("const visibleTrace=visibleCoreEvidence(", access)
        self.assertIn("setTraceEvidence({key:requestKey,value:next})", access)
        self.assertIn("const visibleGraph=visibleCoreEvidence(", access)
        self.assertIn("const diagnosisGeneration=useRef(0),liveGeneration=useRef(0);", operations)
        self.assertIn("const matchingDiagnosis=visibleCoreEvidence(", operations)
        self.assertIn("const matchingLive=visibleCoreEvidence(", operations)
        self.assertIn("if(diagnosisGeneration.current!==token)return;", operations)
        self.assertIn("diagnosisGeneration.current+=1;", operations)
        self.assertIn('setDiagnosisEvidence({key:requestKey,value:result})', operations)
        self.assertIn("if(liveGeneration.current!==token)return;", operations)
        self.assertIn("Live access: UNKNOWN", operations)
        self.assertIn("const cutoffGeneration=useRef(0);", operations)
        self.assertIn("const activeCutoffs=visibleCoreEvidence(", operations)
        self.assertIn("const token=++cutoffGeneration.current;", operations)
        self.assertIn("if(cutoffGeneration.current!==token)return;", operations)
        self.assertIn("setCutoffEvidence({key:plane,value:result})", operations)
        self.assertIn("Cutoff evidence: UNKNOWN", operations)
        self.assertIn("export function coreCutoffKey(", access)
        self.assertIn("const cutoffPlanGeneration=useRef(0);", operations)
        self.assertIn("const currentCutoffPreview=visibleCoreEvidence(", operations)
        self.assertIn("cutoffPlanGeneration.current+=1;", operations)
        self.assertIn("const token=++cutoffPlanGeneration.current;", operations)
        self.assertIn("if(cutoffPlanGeneration.current!==token)return;", operations)
        self.assertIn("setCutoffPreview({key:requestKey,value:result})", operations)
        self.assertIn("change_plan_id:currentCutoffPreview.change_plan_id", operations)
        self.assertIn("disabled={cutoffBusy} onClick={()=>changePlane(value)}", operations)
        self.assertIn("disabled={cutoffBusy||cutoffConfirm!==", operations)

    def test_agent_and_service_preview_rejects_responses_for_changed_host(self):
        remote = (ROOT / "web/src/uxb-remote-service.tsx").read_text(encoding="utf-8")
        enrollment = P0_ENROLL_SOURCE
        # The Host may change while a read-only Core preview is still awaiting
        # a response; obsolete plans must not reappear and become actionable.
        for src, guard in (
            (remote, "requestGeneration"),
            (enrollment, "approvalGeneration"),
        ):
            self.assertIn("const " + guard + "=useRef(0);", src)
            self.assertIn(guard + ".current+=1;", src)
            self.assertIn("const generation=++" + guard + ".current;", src)
            self.assertIn("if(generation!==" + guard + ".current)return;", src)
        self.assertIn('setPreview(null);setConfirmation("");setJob(null)', remote)
        self.assertIn("disabled={busy||fetchBusy}", enrollment)
        self.assertIn("disabled={busy||fetchBusy}", enrollment)

    def test_remote_service_operation_blocks_parent_context_switch(self):
        remote=(ROOT / "web/src/uxb-remote-service.tsx").read_text(encoding="utf-8")
        self.assertIn("onBusyChange?:(busy:boolean)=>void", remote)
        self.assertIn("onBusyChange?.(busy)", remote)
        self.assertIn("onBusyChange?.(false)", remote)
        self.assertIn("onBusyChange={setServiceBusy}", SETUP_SOURCE)
        self.assertIn("disabled={wizardBusy} onClick={()=>changePlane(item.id)}", SETUP_SOURCE)
        self.assertIn("disabled={step===1||wizardBusy}", SETUP_SOURCE)
        self.assertIn("disabled={step===4||wizardBusy}", SETUP_SOURCE)
        self.assertIn("onChange={e=>chooseRemoteHost(e.target.value)}", SETUP_SOURCE)
        self.assertIn("disabled={wizardBusy} onChange={e=>chooseRemoteHost(e.target.value)}", SETUP_SOURCE)

    def test_policy_preview_tests_apply_prevents_wizard_stage_escape(self):
        policy = P0_ACCESS_SOURCE
        self.assertIn("onBusyChange?:(busy:boolean)=>void", policy)
        self.assertIn("onBusyChange?.(busy)", policy)
        self.assertIn("onBusyChange?.(false)", policy)
        self.assertIn("onBusyChange={setPolicyBusy}", SETUP_SOURCE)
        self.assertIn("const wizardBusy=isWizardBusy(serviceBusy,enrollmentBusy,policyBusy);", SETUP_SOURCE)
        self.assertIn('disabled={busy} onClick={()=>onNavigate?.("access","access")}', policy)
        self.assertIn('className="secondary" disabled={busy} onClick={()=>onNavigate?.("objects","access")}', policy)
        self.assertIn('disabled={wizardBusy} onClick={()=>setStep(i+1)}', SETUP_SOURCE)

    def test_enrollment_issue_blocks_parent_wizard_navigation(self):
        self.assertIn("onBusyChange?:(busy:boolean)=>void", P0_ENROLL_SOURCE)
        self.assertIn("onBusyChange?.(busy)", P0_ENROLL_SOURCE)
        self.assertIn("onBusyChange?.(false)", P0_ENROLL_SOURCE)
        self.assertIn("onBusyChange={setEnrollmentBusy}", SETUP_SOURCE)
        self.assertIn("const wizardBusy=isWizardBusy(serviceBusy,enrollmentBusy,policyBusy);", SETUP_SOURCE)
        self.assertIn("disabled={wizardBusy} onClick={()=>changePlane(item.id)}", SETUP_SOURCE)
        self.assertIn("disabled={step===1||wizardBusy}", SETUP_SOURCE)
        self.assertIn("disabled={step===4||wizardBusy}", SETUP_SOURCE)
        self.assertIn("onClick={refreshCore} disabled={checking||wizardBusy}", SETUP_SOURCE)

    def test_one_time_agent_invitation_copy_is_user_initiated_and_ephemeral(self):
        self.assertIn("async function copyIssued(label:string,value:string){", P0_ENROLL_SOURCE)
        self.assertIn("navigator.clipboard.writeText(value)", P0_ENROLL_SOURCE)
        self.assertIn('Copy enrollment code', P0_ENROLL_SOURCE)
        self.assertIn('Copy install command', P0_ENROLL_SOURCE)
        self.assertIn('Clipboard may be visible to other apps.', P0_ENROLL_SOURCE)
        self.assertIn('Copy unavailable. Select the displayed text manually.', P0_ENROLL_SOURCE)
        self.assertIn('setCopyStatus("");setError("");setMessage("");setIssued(null);', P0_ENROLL_SOURCE)
        self.assertNotIn("localStorage", P0_ENROLL_SOURCE)
        self.assertNotIn("sessionStorage", P0_ENROLL_SOURCE)

    def test_first_connection_refresh_ignores_superseded_core_inventory(self):
        self.assertIn("const refreshGeneration=useRef(0);", SETUP_SOURCE)
        self.assertIn("const planeRef=useRef(plane);", SETUP_SOURCE)
        self.assertIn("const generation=++refreshGeneration.current;", SETUP_SOURCE)
        self.assertIn("if(refreshGeneration.current!==generation)return;", SETUP_SOURCE)
        self.assertIn("return()=>{refreshGeneration.current+=1;}", SETUP_SOURCE)
        self.assertIn('if(planeRef.current==="remote")chooseRemoteHost("");', SETUP_SOURCE)
        self.assertIn("selectedHostRef.current=\"\";", SETUP_SOURCE)
        self.assertIn("planeRef.current=value;", SETUP_SOURCE)
        self.assertIn("const restoredDraft=reconcileHostBoundDraft(initialDraft);", SETUP_SOURCE)
        self.assertIn("const [serviceDraft,setServiceDraft]=useState(restoredDraft.service||", SETUP_SOURCE)
        self.assertIn("const [selectedHost,setSelectedHost]=useState(restoredDraft.selectedHost||", SETUP_SOURCE)

    def test_objects_family_returns_to_correct_first_connection_plane(self):
        self.assertIn('export function setupContextForObjectFamily(', NAV_SOURCE)
        self.assertIn('setupContextForObjectFamily(family)||undefined', SOURCE)
        self.assertIn('onNavigate?.("setup","connections",setupContextForObjectFamily(family)||undefined)', SOURCE)
        self.assertIn('function ObjectsWorkspace({data,onNavigate,context,api}', SOURCE)

    def test_uxb_first_use_keeps_three_planes_and_core_authority_separate(self):
        self.assertIn('FirstUseHome data={data}', SOURCE)
        self.assertIn('if(active==="setup"){', SOURCE)
        self.assertIn('return <FirstConnectionSetup api={api}', SOURCE)
        self.assertIn('initialDraft={draft}', SOURCE)
        self.assertIn('context?.plane', SOURCE)
        self.assertIn('className="dr-uxb-nav-advanced"', SOURCE)
        self.assertIn('<summary>Advanced tools</summary>', SOURCE)
        self.assertIn('.dr-uxb-nav-advanced>summary:focus-visible', CSS)
        self.assertIn('const [setupDraft,setSetupDraft]=useState<SetupDraft|null>(null)', SOURCE)
        self.assertIn('onSetupDraftChange={setSetupDraft}', SOURCE)
        self.assertIn('const draft=requestedPlane?', SOURCE)
        self.assertIn('onDraftChange?.({plane,step,selectedHost,serviceName,', SETUP_SOURCE)
        self.assertIn('initialSelection={serviceDraft}', SETUP_SOURCE)
        self.assertIn('firstConnectionStates', HOME_SOURCE)
        for marker in ("PENDING_APPROVAL", "Approved", "Remote Access", "Internet Access", "AI Access"):
            self.assertIn(marker.lower(), (HOME_SOURCE + SETUP_SOURCE).lower())
        self.assertIn('GuidedPolicyJourney key={plane}', SETUP_SOURCE)
        self.assertIn('lockedPlane', SETUP_SOURCE)
        self.assertIn('AccessEvidenceExplorer api={api}', SETUP_SOURCE)
        self.assertIn('canEdit&&selected?<RemoteServiceEditor key={selectedHost} api={api} ownerHint={selectedHost} lockOwner', SETUP_SOURCE)
        self.assertIn('Selected Agent must be observed before publishing', SETUP_SOURCE)
        self.assertIn('Go to Agent selection', SETUP_SOURCE)
        self.assertIn('Publishing for {selected.name||selected.label||selected.hostname||selected.id}', SETUP_SOURCE)
        self.assertIn('const actualOwner=remoteServiceOwner(owner,ownerHint,lockOwner);', (ROOT/"web/src/uxb-remote-service.tsx").read_text())
        self.assertIn('const body:any={owner:actualOwner,name:name.trim(),operation}', (ROOT/"web/src/uxb-remote-service.tsx").read_text())
        self.assertIn('function chooseRemoteHost(nextHost:string)', SETUP_SOURCE)
        self.assertIn('retargetRemoteHost(', SETUP_SOURCE)
        self.assertIn('className="dr-uxb-next-guidance"', SETUP_SOURCE)
        self.assertIn('const nextAction=firstConnectionGuidance(', SETUP_SOURCE)
        self.assertIn('.dr-uxb-next-guidance', CSS)
        self.assertNotIn("localStorage", SETUP_SOURCE + HOME_SOURCE)

    def test_competitor_inspired_first_use_selection_keeps_canonical_core(self):
        chooser=(ROOT / "web/src/uxb-core-choices.tsx").read_text(encoding="utf-8")
        policy=(ROOT / "web/src/p0-access-policy.tsx").read_text(encoding="utf-8")
        service=(ROOT / "web/src/uxb-remote-service.tsx").read_text(encoding="utf-8")
        self.assertIn('CoreChoiceField api={api} catalog={catalog} plane={plane} field="source"', SETUP_SOURCE)
        self.assertIn('CoreChoiceField api={api} catalog={catalog} plane={plane} field="destination"', SETUP_SOURCE)
        self.assertIn('CoreChoiceField api={api} catalog={catalog} plane={plane} field="selector"', SETUP_SOURCE)
        self.assertIn('api("/api/v1/objects-groups?limit=50")', SETUP_SOURCE+chooser)
        self.assertIn('CoreChoiceField api={api} catalog={catalog} plane={plane} field="source"', policy)
        self.assertIn('CoreChoiceField api={api} catalog={catalog} plane="remote" field="selector"', service)
        self.assertIn('disabled={busy} onChoose={value=>edit(setService,value)}', service)
        self.assertIn('disabled={busy} onChoose={v=>changeFlow("source",v)}', policy)
        self.assertIn('aria-pressed={plane===item.id}', SETUP_SOURCE)
        self.assertIn('onNavigate?.("setup","connections",{plane:item.plane})', HOME_SOURCE)
        self.assertIn('const requestedPlane=', SOURCE)
        self.assertIn('if(isFreshInstallation(data))return', SOURCE)
        self.assertIn('data-testid="uxb-fresh-home"', SOURCE)
        self.assertIn('No network access has been verified yet', SOURCE)
        self.assertIn('role="group" aria-label="What are you connecting?"', SETUP_SOURCE)
        self.assertIn('A selection is not approval; Core validates the change.', policy)
        self.assertIn('className="dr-uxb-rule-summary"', policy)
        self.assertIn('className="dr-uxb-manual-fields"', policy)
        self.assertIn('This is an unverified draft.', policy)
        self.assertIn('.dr-uxb-rule-summary', CSS)
        self.assertIn('resourceCatalog={catalog}', SETUP_SOURCE)
        self.assertIn('export async function searchCoreSelectorCatalog(', chooser)
        self.assertIn('"/api/v1/inventory?resource_type="+encodeURIComponent(type)', chooser)
        self.assertIn('+"&q="+encodeURIComponent(needle)+"&limit=50"', chooser)
        self.assertIn('const generation=++requestGeneration.current;', chooser)
        self.assertIn('if(generation!==requestGeneration.current)return;', chooser)
        self.assertIn('Core name search unavailable:', chooser)
        self.assertIn('Find matching names', chooser)
        self.assertIn('api={api} catalog={catalog}', SETUP_SOURCE)
        self.assertIn('api={api} catalog={catalog}', policy)
        self.assertIn('api={api} catalog={catalog}', service)
        self.assertIn('onNavigate?.("objects","access",{family:plane==="ai"?"ai":"network"})', SETUP_SOURCE)
        self.assertIn('onNavigate?.("objects","access",{family:plane==="ai"?"permission":"network"})', SETUP_SOURCE)
        self.assertIn('<ObjectsWorkspace data={data} onNavigate={onNavigate} context={context} api={api}/>', SOURCE)
        self.assertIn('requireObservedObjectContinuation(type,await api(query),cursor,50)', SOURCE)
        self.assertIn('const [nextByType,setNextByType]=useState<Record<string,string|null>>', SOURCE)
        self.assertIn('const generation=++pageEpoch.current;', SOURCE)
        self.assertIn('if(generation!==pageEpoch.current)return;', SOURCE)
        self.assertIn('Object inventory pagination', SOURCE)
        self.assertIn('Load more "+type.replaceAll("-"," ")', SOURCE)
        self.assertIn('const initialFamily=["all","network","service","permission","ai"]', SOURCE)
        self.assertIn('setFamily(initialFamily);setFilter("");setSelected(null)', SOURCE)
        self.assertIn('const incomplete=!resources||requiredTypes.some', SOURCE)
        self.assertIn('const availableTypes=requiredTypes.filter(type=>', SOURCE)
        self.assertIn('const truncated=availableTypes.length>0;', SOURCE)
        self.assertIn('No match in loaded Core resources', SOURCE)
        self.assertIn('Partial Core snapshot · more names exist for', SOURCE)
        self.assertIn('Find another Core name →', SOURCE)
        self.assertIn('.dr-uxb-catalog-page-notice', CSS)
        self.assertNotIn('localStorage.', chooser+SETUP_SOURCE)
        self.assertNotIn('/api/v1/policy/direct-apply', chooser+policy)
        self.assertIn('.dr-uxb-mode-card:focus-visible', CSS)

    def test_uxb_contextual_diagnosis_and_safe_system_disclosure(self):
        # UXB-04 keeps an entity reference in ephemeral shell memory while
        # preserving canonical Core object-vs-host semantics.
        for marker in (
            'setNavigationContext(context||null)',
            'context={navigationContext}', 'context={context}',
            'Investigating {context.originType', 'originType:"access-rule"',
            'originType:isHost?"managed-host":"remote-service"',
            'Why can / cannot connect?', 'Why allowed / denied?',
            'initialPlane=["remote","internet","ai"]',
            'setResource]=useState(String(context?.originId||""))',
        ):
            self.assertIn(marker, SOURCE)
        # UXB-05 keeps Foundation administration visible but hides privileged
        # product-owned controls behind an explicit advanced disclosure.
        self.assertIn('function SystemAdministrationWorkspace(', SOURCE)
        self.assertIn('id="drlink-core-advanced"', SOURCE)
        self.assertIn('<SystemPanel data={data} operator={operator}/>', SOURCE)
        self.assertIn('if(advanced)advanced.open=true', SOURCE)
        self.assertIn('Web HTTPS listener settings are not implemented here', SOURCE)
        self.assertIn('Admin role required', SOURCE)
        # Incomplete Core status must never be presented as an observed zero
        # or a healthy system.
        self.assertIn('Core attention evidence unavailable', SOURCE)
        self.assertIn('const status=coreHealthState(result);', SOURCE)
        self.assertIn('status==="Healthy"?"healthy":status==="Attention"?"attention":"unknown"', SOURCE)
        self.assertIn('UNKNOWN', SOURCE)

    def test_foundation_administration_keeps_support_separate_from_actor_access(self):
        # Foundation's availability is the product capability; access is the
        # authenticated actor's permission. A non-admin must not see a
        # privileged open action or a false claim that users are unsupported.
        component = SOURCE.split("function LinkFoundationAdministration(", 1)[1]
        component = component.split("function SystemPanel(", 1)[0]
        self.assertIn('createLinkFoundationAdministrationTasks(operator.role)', component)
        self.assertIn('import {createLinkFoundationAdministrationTasks}', SOURCE)
        self.assertIn('"core.https":{', ADMIN_SOURCE)
        self.assertIn('"core.users":{', ADMIN_SOURCE)
        https = ADMIN_SOURCE.split('"core.https":{', 1)[1].split('    },', 1)[0]
        users = ADMIN_SOURCE.split('"core.users":{', 1)[1].split('    },', 1)[0]
        self.assertIn('availability:"read_only"', https)
        self.assertIn('access:"view"', https)
        self.assertIn('MCP TLS certificate status only', https)
        self.assertIn('Shared Web HTTPS listener and redirect configuration', https)
        self.assertIn('actionId:"link.certificate"', https)
        self.assertIn('availability:"supported"', users)
        self.assertIn('access:admin?"manage":"none"', users)
        self.assertIn('...(admin?{target:', users)
        self.assertIn('actionId:"link.users"', users)
        self.assertIn('if(admin)onNavigate?.("users","administration")', component)
        self.assertIn('showUnavailable onOpen={openTask}', component)
        for name in (
            "core.password", "core.timezone", "core.network",
            "core.retention", "core.backup-import"
        ):
            self.assertIn(f'"{name}":unavailable', ADMIN_SOURCE)
        for name in ("core.audit", "core.health"):
            self.assertIn(f'"{name}":{{', ADMIN_SOURCE)

    def test_managed_host_admission_is_visible_separately_from_connection(self):
        # An admission filter alone is not enough; the selected state must be
        # visible in the inventory row and independent of connectivity.
        self.assertIn(
            "<th>Admission</th><th>Connection</th><th>Trust</th>", SOURCE
        )
        self.assertIn(
            'item.admission_state==="APPROVED"?"Approved"', SOURCE
        )
        self.assertIn("selected.admission_state", SOURCE)
        self.assertIn('value="PENDING_APPROVAL"', SOURCE)
        self.assertIn('value="QUARANTINED"', SOURCE)

    def test_admission_changes_are_admin_only_and_confirmation_bound(self):
        self.assertIn("function ManagedHostAdmissionPanel()", SOURCE)
        self.assertIn("/api/v1/managed-hosts/admission/preview", SOURCE)
        self.assertIn("/api/v1/managed-hosts/admission/apply", SOURCE)
        self.assertIn('operator.role==="Admin"&&<ManagedHostAdmissionPanel/>', SOURCE)
        self.assertIn('confirmation!==required', SOURCE)
        self.assertIn("active connections are not terminated", SOURCE)

    def test_zero_touch_preapproval_is_explicit_admin_only_and_defaults_off(self):
        self.assertIn('const [preApproved,setPreApproved]=useState(false)', P0_ENROLL_SOURCE)
        self.assertIn('mode==="zero-touch"?{pre_approved:preApproved}:{}', P0_ENROLL_SOURCE)
        self.assertIn('admin&&mode==="zero-touch"', P0_ENROLL_SOURCE)
        self.assertIn('setPreApproved(false);setIssued(null)', P0_ENROLL_SOURCE)
        self.assertIn('Pre-approve first Host from this ticket', P0_ENROLL_SOURCE)
        self.assertIn('data={data} operator={operator} onNavigate={onNavigate} refresh=', SOURCE)

    def test_p0_ux_uses_canonical_core_read_and_change_plans(self):
        self.assertIn('AccessEvidenceExplorer api={api}', SOURCE)
        self.assertIn('GuidedPolicyJourney api={api}', SOURCE)
        self.assertIn('EnrollmentOnboarding api={api}', SOURCE)
        for marker in (
            '/api/v1/policy/trace', '/api/v1/policy/graph',
            '/api/v1/guided/preview', '/api/v1/policy-tests/run',
            '/api/v1/guided/apply', 'required_only:true',
            'canApplyGuidedRule(preview,tests,acknowledge)',
            'Decision: UNKNOWN until a fresh Core decision trace succeeds',
        ):
            self.assertIn(marker, P0_ACCESS_SOURCE)
        for marker in (
            '/api/v1/enrollments/manual', '/api/v1/enrollments/zero-touch',
            '/api/v1/inventory?resource_type=managed-host&limit=100',
            '/api/v1/managed-hosts/admission/preview',
            '/api/v1/managed-hosts/admission/apply',
            'Effective policy reachability:', 'NOT VERIFIED',
        ):
            self.assertIn(marker, P0_ENROLL_SOURCE)
        self.assertNotIn('localStorage', P0_ACCESS_SOURCE + P0_ENROLL_SOURCE)

    def test_agent_update_preview_is_admin_only_and_not_an_apply_surface(self):
        self.assertIn("function AgentRolloutPreviewPanel()", SOURCE)
        self.assertIn(
            'operator.role==="Admin"&&<AgentRolloutPreviewPanel/>', SOURCE
        )
        self.assertIn(
            '/api/v1/jobs/agent-update-rollout/preview', SOURCE
        )
        self.assertIn("Preview only · No updates", SOURCE)
        self.assertIn("Ready to apply: NO", SOURCE)
        self.assertIn("preview.artifact_qualification", SOURCE)
        self.assertIn("preview.blocked_targets", SOURCE)
        self.assertIn("preview.target_observations", SOURCE)
        self.assertIn("Observed version", SOURCE)
        self.assertIn("Update availability remains UNKNOWN", SOURCE)

    def test_agent_rollout_preview_disregards_stale_and_malformed_core_results(self):
        preview=SOURCE.split('function AgentRolloutPreviewPanel(){',1)[1].split('function JobOperations(',1)[0]
        helper=(ROOT / 'web/src/uxb-menu-evidence.ts').read_text(encoding='utf-8')
        self.assertIn('export function requireObservedRolloutPreview(',helper)
        for expected in (
            'const previewGeneration=useRef(0);',
            'const previewInFlight=useRef(false);',
            'previewGeneration.current+=1;',
            'if(previewInFlight.current)return;',
            'const epoch=++previewGeneration.current;',
            'requireObservedRolloutPreview(await api("/api/v1/jobs/agent-update-rollout/preview",',
            'if(epoch!==previewGeneration.current)return;',
            'UNKNOWN · Core Agent Update Preview',
            'disabled={busy||!hosts.trim()',
            'setPreview(null);setError("");',
            'return()=>{previewGeneration.current+=1};',
        ):
            self.assertIn(expected,preview,expected)
        self.assertNotIn('setPreview(await api(',preview)
        self.assertIn('if(epoch===previewGeneration.current){previewInFlight.current=false;setBusy(false)}',preview)

    def test_access_hygiene_orphan_filter_and_resource_navigation(self):
        helper=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn('quality==="ORPHANED"&&x.kind!=="orphan-object"', SOURCE)
        for route in ('"object":{route:"objects",group:"access"}',
                      '"service-account":{route:"integrations",group:"administration"}',
                      '"managed-host":{route:"hosts",group:"connections"}'):
            self.assertIn(route,helper)
        self.assertIn('if(type==="service-account"&&role!=="Admin")return null;',helper)
        self.assertIn('hygieneInspectTarget(x.resource_type,operator.role)', SOURCE)
        self.assertIn('No compatible detail workspace', SOURCE)
        self.assertIn('const unknown=data.summary.unknown_evidence;', SOURCE)
        self.assertIn('data.generated_at', SOURCE)
        self.assertIn('x.observation_window_days===0?"Current"', SOURCE)
        self.assertIn('aria-label="Filter finding severity"', SOURCE)
        self.assertIn('severityFilter!=="all"&&x.severity!==severityFilter', SOURCE)
        self.assertIn('aria-label="Filter finding type"', SOURCE)
        self.assertIn('kindFilter!=="all"&&x.kind!==kindFilter', SOURCE)
        self.assertIn('aria-label="Filter observed age"', SOURCE)
        self.assertIn('ageFilter==="unknown"&&observedAge!==null', SOURCE)
        self.assertIn('observedAge===null||observedAge<Number(ageFilter)', SOURCE)
        self.assertIn('x.age_days==="number"?x.age_days+" days":"Unknown"', SOURCE)
        self.assertIn('<th>Observed age</th><th>Window</th>', SOURCE)

    def test_shell_command_center_and_resource_workspaces_exist(self):
        for marker in (
            "drlink_web_sidebar_collapsed",
            "drlink_web_theme",
            "dr-topbar",
            "dr-command-palette",
            "Command Center",
            "Recent Activity",
            "Recent Changes",
            "dr-detail-drawer",
            "Access Workspace",
            "Policy Simulator",
            "Filter hosts",
            "Filter services",
            "Filter loaded objects and groups",
            "Filter policies",
            "Skip to content",
            "drlink-main-content",
            "dr-page-skeleton",
            "dr-sidebar-signout",
        ):
            self.assertTrue(marker in SOURCE or marker in CSS, marker)

    def test_owner_review_pages_use_spacious_structured_workspaces(self):
        for source_marker in (
            "dr-fleet-card",
            "Target scope",
            "Group membership",
            "dr-audit-filter-grid",
            "Audit Retention",
            "HealthWorkspace",
            "Advanced · raw health payload",
            "temporary setup key is not active until you verify",
            "QRCodeSVG",
            "1. Scan the QR code",
            "Nothing is sent to an external QR service",
            "/api/v1/auth/mfa/enroll/cancel",
            "Show key",
            "Recovery codes are issued only after verification succeeds",
        ):
            self.assertIn(source_marker, SOURCE)
        for style_marker in (
            ".dr-form-grid.two",
            ".dr-audit-filter-grid",
            ".dr-health-summary",
            ".dr-mfa-secret-row",
            ".dr-mfa-qr-panel",
        ):
            self.assertIn(style_marker, CSS)
        self.assertIn('"qrcode.react"', PACKAGE)
        self.assertIn('"node_modules/qrcode.react"', PACKAGE_LOCK)
        self.assertIn('"version": "4.2.0"', PACKAGE_LOCK)

    def test_responsive_and_keyboard_contract_is_present(self):
        for marker in (
            "@media(max-width:850px)",
            "@media(max-width:560px)",
            ".dr-skip-link",
            ".dr-detail-drawer:focus-visible",
        ):
            self.assertIn(marker, CSS)
        self.assertIn('(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"', SOURCE)
        self.assertIn('if(e.key==="Escape")onClose()', SOURCE)
        self.assertIn('tabIndex={-1} autoFocus', SOURCE)

    def test_uxb_global_search_keeps_keyboard_focus_inside_modal(self):
        # Static integration guard only; the real 320/375px browser keyboard
        # scenario still requires authenticated human acceptance (UXE-10).
        dialog = SOURCE.split("function GlobalSearch(", 1)[1].split("function Shell(", 1)[0]
        shell = SOURCE.split("function Shell(", 1)[1].split("function App(", 1)[0]
        for required in (
            'ref={dialogRef} tabIndex={-1}',
            'role="dialog" aria-modal="true"',
            'if(e.key!=="Tab"||!dialogRef.current)return;',
            "dialog.querySelectorAll<HTMLElement>",
            'element.getClientRects().length>0',
            'if(e.shiftKey&&(active===first||!dialog.contains(active)))',
            'else if(!e.shiftKey&&(active===last||!dialog.contains(active)))',
            'e.preventDefault();last.focus();',
            'e.preventDefault();first.focus();',
            'if(e.key==="Escape")',
            "onCloseRef.current();",
            "else if(target?.isConnected){",
            "target.focus();",
            "returnFocusRef.current=null;",
        ):
            self.assertIn(required, dialog, required)
        for required in (
            'searchReturnFocusRef=useRef<HTMLElement|null>(null)',
            'searchReturnFocusRef.current=invoker||(',
            'document.activeElement instanceof HTMLElement',
            'if(!searchOpen)openSearch();',
            'onClick={e=>openSearch(e.currentTarget)}',
            'returnFocusRef={searchReturnFocusRef}',
        ):
            self.assertIn(required, shell, required)

    def test_uxb_search_result_navigation_and_feedback_are_accessible(self):
        # Source guard; human keyboard and assistive-tech browser E2E is separate.
        dialog = SOURCE.split("function GlobalSearch(", 1)[1].split("function Shell(", 1)[0]
        for marker in (
            'const navigatingRef=useRef(false);',
            'if(!visibleRoute(id,operator.role)){',
            'setError("Your role cannot open this page.");',
            'navigatingRef.current=true;',
            'if(navigatingRef.current){',
            'document.getElementById("drlink-main-content")?.focus();',
            'target.focus();',
            'className="dr-command-error" role="alert"',
            'role="status" aria-live="polite"',
            'role="group" aria-label="Core resource matches" aria-busy={busy}',
        ):
            self.assertIn(marker, dialog, marker)
        self.assertLess(
            dialog.index('if(!visibleRoute(id,operator.role)){'),
            dialog.index('navigatingRef.current=true;'),
        )
        self.assertLess(
            dialog.index('navigatingRef.current=true;'),
            dialog.index('onNavigate(id,group);'),
        )
        self.assertIn('id="drlink-main-content"', SOURCE)
        self.assertIn('tabIndex={-1}', SOURCE)

    def test_uxb_menu_observation_does_not_hide_missing_core_collections(self):
        # Static UI integration check; the new independent Node tests exercise
        # valid/invalid response values. Neither substitutes for human E2E.
        helper = (ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("function requireObservedMenuPayload(", helper)
        for page in ("hosts", "services", "policies", "enrollments",
                     "hygiene", "jobs", "audit", "revisions", "views", "users",
                     '"service-accounts"', "webhooks"):
            self.assertIn(page + ':', helper)
        self.assertIn('!Array.isArray(value.items)', helper)
        self.assertIn('State is UNKNOWN, not an empty list', helper)
        self.assertIn('function isPartialCorePage(', helper)
        self.assertIn('from "./uxb-menu-evidence"', SOURCE)
        self.assertIn('requireObservedInventoryContinuation(route,await api(path),requestedCursor,100)', SOURCE)
        self.assertIn('<ResourceWorkspace kind="host" data={data}', SOURCE)
        self.assertIn('<ResourceWorkspace kind="service" data={data}', SOURCE)
        self.assertIn('Load more Managed Hosts →', SOURCE)
        self.assertIn('Load more Remote Services →', SOURCE)
        self.assertIn('Next Core inventory page unavailable', SOURCE)
        self.assertIn('setCursor(isPartialCorePage(page)?page.next_cursor:null)', SOURCE)
        self.assertIn('if(epoch!==loadEpoch.current)return;', SOURCE)
        self.assertIn('Core policy list may be incomplete', SOURCE)
        self.assertIn('Partial Core inventory', SOURCE)
        self.assertIn('No match in loaded policy rules', SOURCE)
        self.assertIn('No match in loaded resources', SOURCE)
        self.assertIn('setData(active==="hygiene"?requireObservedAccessHygiene(payload):requireObservedMenuPayload(active,payload))', SOURCE)
        self.assertIn('if(!current)return;', SOURCE)
        self.assertIn('return()=>{current=false}', SOURCE)
        self.assertIn('Core data unavailable · UNKNOWN', SOURCE)
        self.assertIn('Retry Core read →', SOURCE)
        self.assertIn('requireObservedMenuPayload("jobs",await api("/api/v1/jobs?limit=50"+', SOURCE)
        self.assertIn('if(epoch!==jobsReadEpoch.current)return;', SOURCE)
        self.assertIn('useEffect(()=>{refresh();return()=>{jobsReadEpoch.current+=1}},[jobsCursor]);', SOURCE)
        self.assertIn('setJobsHistory([...jobsHistory,jobsCursor])', SOURCE)
        self.assertIn('setJobsCursor(jobs.next_cursor)', SOURCE)
        self.assertIn('setJobsCursor(jobsHistory[jobsHistory.length-1])', SOURCE)
        self.assertIn('aria-label="Jobs pagination"', SOURCE)
        self.assertIn('Older Jobs →', SOURCE)
        self.assertIn('← Newer Jobs', SOURCE)
        self.assertIn('Access · Advanced', SOURCE)
        self.assertIn('jobsState!=="ready"', SOURCE)
        self.assertIn('UNKNOWN · Core Jobs inventory is unavailable.', SOURCE)
        for name in ("enrollments", "views"):
            self.assertIn('requireObservedMenuPayload("'+name+'",payload)', SOURCE)
        self.assertIn('setData(requireObservedAccessHygiene(payload))', SOURCE)

    def test_administration_inventory_failures_never_show_fake_empty_users_or_integrations(self):
        # Integration source contract: do not conceal auth/API errors as empty data.
        users = SOURCE.split("function UsersPanel(", 1)[1].split("function IntegrationsPanel(", 1)[0]
        integrations = SOURCE.split("function IntegrationsPanel(", 1)[1].split("function CommandCenter(", 1)[0]
        for expected in (
            'const [data,setData]=useState<any>(null)',
            'setData(requireObservedMenuPayload("users",await api("/api/v1/operators")))',
            'catch(e:any){setData(null);setError(e.message||String(e))}',
            'if(!data)return <section className="card"',
            'Users inventory unavailable. No empty result was confirmed.',
            'Retry Users read →',
        ):
            self.assertIn(expected, users, expected)
        for expected in (
            'const [inventoryState,setInventoryState]=useState<"loading"|"ready"|"unknown">',
            'requireObservedMenuPayload("service-accounts",a)',
            'requireObservedMenuPayload("webhooks",w)',
            'setInventoryState("ready");',
            'setInventoryState("unknown");',
            'inventoryState!=="ready"?',
            'No empty list has been confirmed.',
            'Retry integrations read →',
            'Copy once: {once.kind}',
            'readOnly value={once.secret}',
        ):
            self.assertIn(expected, integrations, expected)

    def test_uxb_audit_api_failure_is_not_a_fabricated_empty_history(self):
        audit = SOURCE.split("function AuditExplorer(", 1)[1].split("function AgentRolloutPreviewPanel(", 1)[0]
        for expected in (
            'const auditReadEpoch=useRef(0);',
            'const epoch=++auditReadEpoch.current;',
            'setData(null);setAuditState("loading");',
            'requireObservedMenuPayload("audit",await api("/api/v1/audit?"+q.toString()))',
            'if(epoch!==auditReadEpoch.current)return;',
            'setData(page);setAuditPage(position);setAuditFilterKey(filterKey);setAuditState("ready");',
            'setData(null);setAuditState("unknown");',
            'auditState==="ready"?<Table items={rows}/>',
            'UNKNOWN · Core Audit inventory unavailable.',
            'const [auditPage,setAuditPage]=useState<MenuPagePosition>',
            'const [auditFilterKey,setAuditFilterKey]=useState<string|null>(null);',
            'setData(page);setAuditPage(position);setAuditFilterKey(filterKey);setAuditState("ready");',
            'auditFilterKey!==filterParams().toString()',
            'role="group" aria-label="Audit pagination"',
            'selectMenuPage(auditPage,data?.next_cursor,"newer")',
            'selectMenuPage(auditPage,data.next_cursor,"older")',
            'Filters changed since the loaded Audit page.',
            'auditReadEpoch.current+=1;setData(null);setAuditState("idle");setAuditPage({cursor:"",history:[]});setAuditFilterKey(null);setError("");',
            'Filters cleared. Select Search audit to load current Core records.',
        ):
            self.assertIn(expected, audit, expected)

    def test_audit_retention_missing_core_evidence_is_unknown_and_never_normal_zero(self):
        audit = SOURCE.split("function AuditExplorer(", 1)[1].split("function AgentRolloutPreviewPanel(", 1)[0]
        evidence=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("export function requireObservedAuditRetention(", evidence)
        for marker in (
            'const [retentionState,setRetentionState]=useState<"loading"|"ready"|"unknown">("loading");',
            'const retentionReadEpoch=useRef(0);',
            'requireObservedAuditRetention(await api("/api/v1/audit/retention"))',
            'setRetention(null);setRetentionState("unknown");',
            'retentionState==="ready"&&retention&&',
            'retentionState==="unknown"&&',
            'Retry Audit Retention read',
            'disabled={retentionState!=="ready"',
            'setRetention(null);setRetentionState("loading");',
        ):
            self.assertIn(marker,audit,marker)
        for false_status in ('retention.total_events||0','retention.db_size_bytes||0',
                             '{retention&&<div className="dr-kpi-strip'):
            self.assertNotIn(false_status,audit)
        self.assertIn('retentionState==="ready"&&retention&&<div className="dr-kpi-strip',audit)
        self.assertIn('retention.capacity_exceeded?"Exceeded":"Normal"',audit)

    def test_audit_export_requires_matching_core_ack_and_no_false_download(self):
        audit=SOURCE.split("function AuditExplorer(",1)[1].split("function AgentRolloutPreviewPanel(",1)[0]
        evidence=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("export function requireObservedAuditExport(",evidence)
        for marker in (
            'const exportInFlight=useRef(false);',
            'const [exportBusy,setExportBusy]=useState(false)',
            'if(exportInFlight.current)return;',
            'const selectedFilters=exportFilters();',
            'requireObservedAuditExport(await api("/api/v1/audit/export",',
            'selectedFilters)',
            'setExportResult(null);',
            'Core Audit Export status UNKNOWN',
            'No Web download',
            'disabled={exportBusy}',
            'filters:exportResult.filters',
        ):
            self.assertIn(marker,audit,marker)
        self.assertNotIn('setMessage("Audit export created: "+String(value.path||""))',audit)

    def test_inventory_export_requires_authoritative_bounded_artifact_receipt(self):
        job = SOURCE.split("function JobOperations(", 1)[1].split("function ResourceWorkspace(", 1)[0]
        helper = (ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("export function requireObservedInventoryExport(", helper)
        for marker in (
            "const inventoryExportInFlight=useRef(false);",
            "const [inventoryExportBusy,setInventoryExportBusy]=useState(false);",
            "if(inventoryExportInFlight.current)return;",
            'requireObservedInventoryExport(await api("/api/v1/inventory/export",',
            "setInventoryExport(null);",
            "Core Inventory Export status UNKNOWN",
            'disabled={inventoryExportBusy}',
            "No Web download",
            "record_count:inventoryExport.record_count",
            "limits:inventoryExport.limits",
        ):
            self.assertIn(marker, job)
        self.assertNotIn('setMessage("Inventory export created at "+String(result.path||""))',job)

    def test_fleet_preview_never_survives_changed_target_or_stale_response(self):
        jobs=SOURCE.split("function JobOperations(",1)[1].split("function ObjectsWorkspace(",1)[0]
        for marker in (
            'const fleetPreviewEpoch=useRef(0);',
            'const [fleetPreviewBusy,setFleetPreviewBusy]=useState(false);',
            'const [fleetPreviewKey,setFleetPreviewKey]=useState<string|null>(null);',
            'const fleetDraftKey=JSON.stringify([',
            'function invalidateFleetReview(){',
            'fleetPreviewEpoch.current+=1;',
            'const epoch=++fleetPreviewEpoch.current;',
            'const requestedKey=fleetDraftKey;',
            'if(epoch!==fleetPreviewEpoch.current)return;',
            'setFleetPreviewKey(requestedKey);',
            'if(!fleetPreviewGuard||fleetConfirm!=="APPLY")return;',
            'const fleetPreviewGuard=',
            'const fleetApplyInFlight=useRef(false);',
            'if(fleetApplyInFlight.current)return;',
            'const request={resource_type:fleetResourceType,resource:fleetResource,changes};',
            'Fleet tags must be a JSON object with text keys and text values.',
            'Enter a description, tags or group membership change before Preview.',
            'requireObservedFleetPreview(await api("/api/v1/fleet/metadata/preview",',
            'requireObservedFleetApplyForPreview(await api("/api/v1/fleet/metadata/apply",',
            'setFleetPreviewKey(null);',
            'disabled={fleetPreviewBusy||fleetApplyBusy',
            'disabled={!fleetPreviewGuard||fleetConfirm!=="APPLY"}',
        ):
            self.assertIn(marker,jobs,marker)
        self.assertNotIn('onChange={e=>{setFleetResource(e.target.value);setFleetPreview(null)}}',jobs)
        self.assertNotIn('setFleetPreview(result);\n    }catch(e:any)',jobs)

    def test_jobs_detail_and_cancel_never_reuse_stale_core_evidence(self):
        jobs=SOURCE.split("function JobOperations(",1)[1].split("function ObjectsWorkspace(",1)[0]
        helper=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("export function requireObservedJobDetail(",helper)
        self.assertIn("export function requireObservedJobCancellation(",helper)
        for marker in (
            'const detailReadEpoch=useRef(0);',
            'const cancelInFlight=useRef(false);',
            'const [detailBusy,setDetailBusy]=useState(false);',
            'const [cancelBusy,setCancelBusy]=useState(false);',
            'requireObservedJobDetail(await api("/api/v1/jobs/"+encodeURIComponent(target)),target)',
            'if(epoch!==detailReadEpoch.current)return;',
            'detailReadEpoch.current+=1;',
            'requireObservedJobCancellation(await api("/api/v1/jobs/cancel",',
            'Cancellation request recorded; running targets may still finish.',
            'Already terminal; no new cancellation was applied.',
            'UNKNOWN · Core Job cancellation response',
            'disabled={detailBusy||cancelBusy}',
        ):
            self.assertIn(marker,jobs,marker)
        self.assertIn('const result=requireObservedJobDetail(await api(',jobs)
        self.assertIn('if(epoch!==detailReadEpoch.current)return;',jobs)
        self.assertNotIn('setMessage("Cancellation requested. Queued targets are cancelled;',jobs)

    def test_irreversible_retention_requires_typed_confirmation_and_fresh_policy(self):
        audit=SOURCE.split("function AuditExplorer(",1)[1].split("function AgentRolloutPreviewPanel(",1)[0]
        helper=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        self.assertIn("export function auditRetentionRunPermitted(",helper)
        for marker in (
            'const [retentionConfirmation,setRetentionConfirmation]=useState("");',
            'if(!auditRetentionRunPermitted(',
            'value={retentionConfirmation}',
            'Type RUN RETENTION to confirm',
            'retentionEdited&&',
            'Unsaved retention policy changes',
            'onChange={e=>{setControlDays(e.target.value);setRetentionConfirmation("")}}',
            'setRetentionConfirmation("");',
            'disabled={!retentionRunAllowed}',
        ):
            self.assertIn(marker,audit,marker)
        self.assertIn('confirmation!=="RUN RETENTION"',helper)
        self.assertIn('value.config.control_days',helper)
        self.assertIn('value.config.access_days',helper)
        self.assertIn('value.config.max_events',helper)
        self.assertIn('"/api/v1/audit/retention/run"',audit)

    def test_access_hygiene_requires_observed_count_and_true_inspect_target(self):
        helper=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        view=SOURCE.split("function AccessHygienePanel(", 1)[1].split("function SystemAdministrationWorkspace(", 1)[0]
        for marker in (
            'export function requireObservedAccessHygiene(',
            'export function hygieneInspectTarget(',
            'if(type==="service-account"&&role!=="Admin")return null;',
            'authoritative!==false||page.read_only!==true||page.auto_mutation!==false',
        ):
            self.assertIn(marker,helper,marker)
        for marker in (
            'requireObservedAccessHygiene(payload)',
            'const unknown=data.summary.unknown_evidence;',
            'Metric label="Review findings" value={data.count}',
            'const partial=data.count>source.length;',
            'Some Core findings were not included in this bounded read',
            'hygieneInspectTarget(x.resource_type,operator.role)',
            'No compatible detail workspace',
            'Admin role required',
        ):
            self.assertIn(marker,SOURCE,marker)
        self.assertNotIn('data?.count||0',view)
        self.assertNotIn('data?.summary?.unknown_evidence??',view)

    def test_jobs_and_fleet_web_responses_must_have_true_core_confirmation(self):
        evidence=(ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        jobs=SOURCE.split("function JobOperations(",1)[1].split("function ObjectsWorkspace(",1)[0]
        for marker in (
            "export function requireObservedJobStart(",
            "export function requireObservedFleetApply(",
            'job.status!=="QUEUED"',
            'value.status!=="APPLIED"',
            'result.target_count',
        ):
            self.assertIn(marker,evidence,marker)
        for marker in (
            "requireObservedJobStart(await api(",
            "requireObservedFleetApplyForPreview(await api(",
            "Core job request accepted",
            "UNKNOWN · Core Job start response",
            "UNKNOWN · Fleet metadata apply response",
            "setFleetPreview(null);setFleetPreviewKey(null);setFleetConfirm(\"\");",
            'const [fleetApplyBusy,setFleetApplyBusy]=useState(false);',
            'disabled={!fleetPreviewGuard||fleetConfirm!=="APPLY"}',
        ):
            self.assertIn(marker,jobs,marker)
        self.assertNotIn('result.selection?.target_count||0',jobs)
        self.assertNotIn('result.result?.target_count||0',jobs)

    def test_policy_read_does_not_hide_internet_and_ai_behind_remote_limit(self):
        helper = (ROOT / "web/src/uxb-menu-evidence.ts").read_text(encoding="utf-8")
        view = SOURCE.split("function View(", 1)[1].split("function WorkspaceIcon(", 1)[0]
        policy = SOURCE.split("function PolicyWorkspace(", 1)[1].split("function ResourceWorkspace(", 1)[0]
        for marker in (
            'function combineObservedPolicyPlanes(',
            'const planes=["remote","internet","ai"]',
            'page.plane!==planes[i]||page.limit!==limit',
            'possibly_truncated_planes.push(planes[i])',
        ):
            self.assertIn(marker, helper, marker)
        for marker in (
            'if(active==="policies"){',
            'Promise.all(["remote","internet","ai"].map(plane=>',
            '"/api/v1/policies?plane="+plane+"&limit=100"',
            'setData(combineObservedPolicyPlanes(pages,100))',
            'if(!current)return;',
        ):
            self.assertIn(marker, view, marker)
        for marker in (
            'data.possibly_truncated_planes',
            'selectedMayBeLimited',
            'Core policy list may be incomplete',
            'No match in loaded policy rules',
            'const [nextByPlane,setNextByPlane]=useState<Record<string,string|null>>',
            'const [additional,setAdditional]=useState<any[]>([])',
            'async function loadMore(planeName:string){',
            'const cursor=nextByPlane[planeName];',
            'requireObservedMenuPayload("policies",await api(query))',
            'page.plane!==planeName||page.limit!==100',
            'page.items.some((row:any)=>row.plane!==planeName)',
            'Load more "+kind+" rules',
            'if(!page.next_cursor)setExhausted',
        ):
            self.assertIn(marker, policy, marker)

    def test_uxb_change_history_uses_observed_core_pagination(self):
        revisions=(ROOT / "web/src/uxb-revisions.tsx").read_text(encoding="utf-8")
        self.assertIn('import {RevisionHistory} from "./uxb-revisions"', SOURCE)
        self.assertIn('if(active==="revisions"&&data)return <RevisionHistory initial={data} api={api}/>', SOURCE)
        self.assertIn('revisions:"/api/v1/revisions?limit=100"', SOURCE)
        for marker in (
            'requireObservedMenuPayload("revisions",initial)',
            'requireObservedMenuPayload("revisions",await api(url))',
            'const epoch=++requestEpoch.current;',
            'if(epoch!==requestEpoch.current)return;',
            'return()=>{requestEpoch.current+=1};',
            'setPage(null);setLoading(true);setError("");',
            'setRequested(target);',
            'selectMenuPage(position,page.next_cursor,"older")',
            'selectMenuPage(position,page.next_cursor,"newer")',
            'Core Change History unavailable',
            'Retry Core page →',
            'Older revisions →',
            '← Newer revisions',
            'No configuration revisions on this observed Core page.',
        ):
            self.assertIn(marker, revisions, marker)

    def test_change_history_invalid_initial_core_page_renders_unknown_not_exception(self):
        revisions=(ROOT / "web/src/uxb-revisions.tsx").read_text(encoding="utf-8")
        for marker in (
            "export function validateObservedRevisionPage(",
            'page.resource_type!=="revision"||page.limit!==100',
            'let first:any=null,initialIssue="";',
            'try{first=validateObservedRevisionPage(requireObservedMenuPayload("revisions",initial))}',
            'catch(e:any){initialIssue=e.message||String(e)}',
            'setPage(null);setError(e.message||String(e));',
            'const observed=validateObservedRevisionPage(requireObservedMenuPayload("revisions",await api(url)));',
            'UNKNOWN · Core Change History unavailable',
            'Retry Core page →',
        ):
            self.assertIn(marker,revisions,marker)
        self.assertIn('tests/uxb-revisions.test.mjs',PACKAGE)

    def test_agent_version_drift_is_not_synthetic_when_server_version_unknown(self):
        versions=(ROOT / "web/src/uxb-versions.tsx").read_text(encoding="utf-8")
        self.assertIn('import {AgentVersionDrift} from "./uxb-versions";', SOURCE)
        self.assertIn('if(active==="versions"&&data)return <AgentVersionDrift data={data} onNavigate={onNavigate}/>', SOURCE)
        for marker in (
            'function observedVersionState(server:unknown,agent:unknown)',
            'if(!good(server)||!good(agent))return "UNKNOWN";',
            'function validatedVersionInventory(payload:unknown)',
            'No Agent can be classified as matching or different',
            'do not interpret the Core drift count as zero problems',
            'Partial Core version snapshot possible',
            'View Servers &amp; Agents →',
            'data.hosts.length>Number(data.limit)',
            'row.comparison==="DIFFERENT"',
            'observed Agent records',
        ):
            self.assertIn(marker, versions, marker)
        self.assertIn("tests/uxb-versions.test.mjs", PACKAGE)

    def test_core_doctor_distinguishes_absent_checks_from_pass(self):
        doctor=(ROOT / "web/src/uxb-doctor.tsx").read_text(encoding="utf-8")
        self.assertIn('import {CoreDoctorWorkspace} from "./uxb-doctor";', SOURCE)
        self.assertIn('if(active==="doctor"&&data)return <CoreDoctorWorkspace data={data} onNavigate={onNavigate}/>', SOURCE)
        for marker in (
            'function validatedDoctorEvidence(payload:unknown)',
            'report.read_only!==true||report.side_effect_free!==true',
            '||!Array.isArray(report.checks)',
            'row.status==="PASS"?"PASS":',
            'row.status==="ATTENTION"?"ATTENTION":"UNKNOWN"',
            'No runtime generation checks were observed',
            'not proof of healthy access or policy deployment',
            'UNKNOWN · Some Core check states could not be classified',
            'System Health →',
            'Management Jobs →',
            'Other Core attention',
        ):
            self.assertIn(marker, doctor, marker)
        self.assertIn("tests/uxb-doctor.test.mjs", PACKAGE)

    def test_saved_views_can_open_explicit_non_security_resource_filters(self):
        saved=(ROOT / "web/src/uxb-saved-views.tsx").read_text(encoding="utf-8")
        self.assertIn('import {SavedViewsWorkspace,saveDraftForResource,isSavedAdmission,type HostAdmission} from "./uxb-saved-views"', SOURCE)
        self.assertIn('if(active==="views"&&data)return <SavedViewsWorkspace data={data} api={api} onNavigate={onNavigate}', SOURCE)
        self.assertIn('initialFilter={String(context?.savedFilter||"").slice(0,120)}', SOURCE)
        self.assertIn('useEffect(()=>{setFilter(initialFilter)},[kind,initialFilter]);', SOURCE)
        for marker in (
            'export function readSavedView(value:unknown)',
            'payload.resource_type==="managed-host"',
            'payload.resource_type==="remote-service"',
            'onNavigate?.(parsed.route,"connections",{savedFilter:parsed.filter,savedAdmission:parsed.admission||"all"})',
            'payload:currentDraft',
            'Legacy/unsupported view; save a new named target',
            'private display preferences, never access policies',
            'does not fetch missing inventory pages',
        ):
            self.assertIn(marker, saved, marker)
        self.assertIn("tests/uxb-saved-views.test.mjs", PACKAGE)

    def test_saved_views_can_capture_live_resource_filter_without_policy_mutation(self):
        saved=(ROOT / "web/src/uxb-saved-views.tsx").read_text(encoding="utf-8")
        self.assertIn("export function saveDraftForResource(kind:", saved)
        self.assertIn("initialDraft?:unknown", saved)
        self.assertIn('const prepared=readSavedView({payload:initialDraft});', saved)
        self.assertIn('onNavigate?.("views","activity",{savedViewDraft:savedDraft})', SOURCE)
        self.assertIn('initialDraft={context?.savedViewDraft}', SOURCE)
        self.assertIn('Save this view →', SOURCE)
        self.assertIn('maxLength={120}', SOURCE)
        self.assertIn('Pre-filled from', saved)

    def test_saved_view_optional_host_admission_without_security_policy_mutation(self):
        saved=(ROOT / "web/src/uxb-saved-views.tsx").read_text(encoding="utf-8")
        self.assertIn('export type HostAdmission="all"|"PENDING_APPROVAL"|"APPROVED"|"QUARANTINED"', saved)
        self.assertIn('export function isSavedAdmission(value:unknown)', saved)
        self.assertIn('const currentDraft=saveDraftForResource(', saved)
        self.assertIn('payload:currentDraft', saved)
        self.assertIn('Filter Managed Host admission', saved)
        self.assertIn('setAdmission("all")', saved)
        self.assertIn('savedAdmission:parsed.admission||"all"', saved)
        self.assertIn('initialAdmission={context?.savedAdmission}', SOURCE)
        self.assertIn('isSavedAdmission(initialAdmission)', SOURCE)
        self.assertIn('isHost?admissionFilter:"all"', SOURCE)
        self.assertIn('Save this view →', SOURCE)
        self.assertNotIn('Host admission selection is not included.', SOURCE)
        self.assertNotIn('method:"PUT"', saved)

    def test_managed_host_detail_allowlist_and_operator_groups(self):
        helper=(ROOT / "web/src/uxb-host-detail.ts").read_text(encoding="utf-8")
        stylesheet=(ROOT / "web/dist/styles.css").read_text(encoding="utf-8")
        self.assertIn('hostDetailSections(selected).map(', SOURCE)
        self.assertIn('className="dr-host-detail-section"', SOURCE)
        self.assertIn('import {hostDetailSections} from "./uxb-host-detail"', SOURCE)
        self.assertIn(".dr-host-detail-section", stylesheet)
        self.assertIn("Trust & Admission", helper)
        self.assertIn("Connectivity & Version", helper)
        self.assertIn("admission_state", helper)
        self.assertIn("connected===false", helper)
        self.assertNotIn("Object.entries", helper)
        self.assertIn("tests/uxb-host-detail.test.mjs", PACKAGE)
        self.assertIn("Recent activity", SOURCE)
        self.assertIn("Why can / cannot connect?", SOURCE)

    def test_saved_view_name_replacement_requires_explicit_review(self):
        saved=(ROOT / "web/src/uxb-saved-views.tsx").read_text(encoding="utf-8")
        for marker in (
            "export function conflictingSavedViewName(",
            "const duplicate=conflictingSavedViewName(rows,name);",
            "const [confirmReplace,setConfirmReplace]=useState(false);",
            "if(duplicate&&!confirmReplace)return;",
            'setConfirmReplace(false);',
            "Replace existing saved filter",
            "checked={confirmReplace}",
            "disabled={busy||!name.trim()||!currentDraft||!!(duplicate&&!confirmReplace)||incompleteNames&&!confirmReplace}",
            "if(incompleteNames&&!confirmReplace)return;",
            'setName(e.target.value);setConfirmReplace(false);',
            'setFilter(e.target.value);setConfirmReplace(false)',
            "existing name in your observed private list",
        ):
            self.assertIn(marker,saved,marker)
        self.assertNotIn('method:"PUT"',saved)

    def test_normative_ux_doc_binds_control_reference_and_competitive_sources(self):
        for required in (
            "Product Foundation PF-5B Administration projection",
            "**Access & security**", "**Platform & network**",
            "**Lifecycle & recovery**", "**Operations & audit**",
            "MCP TLS", "Web HTTPS listener/redirect configuration",
            "actual browser/mobile accessibility"
        ):
            self.assertIn(required.lower(), UX.lower())
        self.assertIn("DRL3-7A", UX)
        self.assertIn("41a561b769fb589f081e84ec5014de6f48881985", UX)
        self.assertIn("frontend/src/foundation-semantic-tokens.css", UX)
        self.assertIn("frontend/src/components/layout/sidebar.tsx", UX)
        self.assertIn("frontend/src/components/layout/top-header.tsx", UX)
        for product in (
            "Cloudflare One",
            "Palo Alto Strata Cloud Manager",
            "NetBird",
            "Twingate",
            "Tailscale",
            "Teleport",
            "HashiCorp Boundary",
            "Netskope",
            "NordLayer",
        ):
            self.assertIn(product, UX)


if __name__ == "__main__":
    unittest.main()
