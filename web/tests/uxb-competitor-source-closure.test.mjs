// Canonical DataRelay Link 3.0 COMPETITOR-UI SOURCE adoption audit.
// IMPORTANT: asserting source presence is NEVER Browser, installed Core or user E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync,existsSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
const web=dirname(dirname(fileURLToPath(import.meta.url))),root=dirname(web);
const md=rel=>readFileSync(join(root,"docs",rel),"utf8");
const src=rel=>readFileSync(join(web,"src",rel),"utf8");
const matrix=md("COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md");
const ledger=md("COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md");
const main=src("main.tsx");
const path=src("p0-access-policy.tsx");
const ui06=src("uxb-temporary-access-requests-panel.tsx");

test("Competitor UI source closure declares all 8 UX, all 6 UI and every evidence slot CUI-001..040",()=>{
 for(let i=1;i<=8;i++)assert.ok(matrix.includes("UX-"+i+" "),String(i));
 for(let i=1;i<=6;i++)assert.ok(matrix.includes("UI-0"+i+" "),String(i));
 for(let i=1;i<=40;i++){
  const slot="CUI-"+String(i).padStart(3,"0");
  assert.ok(matrix.includes(slot),slot+" missing from canonical adoption crosswalk");
 }
 assert.match(matrix,/CUI-027\*/);
 assert.match(matrix,/CUI-028\*/);
 assert.match(matrix,/original ledger did not print literal CUI-027\/CUI-028/i);
 assert.match(ledger,/G-37 P0-2 delivered/);
});

test("Every vendor in the actual 13-product audit has an explicit adopt/preserve/reject/gate disposition",()=>{
 for(const vendor of ["Tailscale","NetBird","Twingate","Teleport","Cloudflare One","StrongDM",
  "HashiCorp Boundary","BeyondTrust PRA","Zscaler ZPA","Palo Alto Prisma",
  "NordLayer","Appgate SDP","JumpCloud"]){
  assert.ok(matrix.includes("| "+vendor),vendor);
 }
 for(const value of ["APPLIED","PRESERVED","REJECTED","SECURITY GATE"])
  assert.ok(matrix.includes(value),value);
});

test("Adopted UI implementation has original Link code for explain/change/enroll/audit/Home/Policy/Saved Views",()=>{
 assert.match(path,/function AccessEvidenceExplorer\(/);
 assert.match(path,/focusCoreModeledPaths\(/);
 assert.match(path,/function GuidedPolicyJourney\(/);
 assert.match(path,/Verified Core publication edges/);
 assert.match(src("p0-enrollment.tsx"),/EnrollmentOnboarding/);
 assert.match(main,/function CommandCenter\(/);
 assert.match(main,/const overviewEvidence=observedCoreOverviewEvidence\(data\)/);
 assert.match(main,/onNavigate\?\.\(x.route,x.group\)/);
 assert.match(main,/onNavigate\?\.\("policies","access",\{plane:row.key\}\)/);
 assert.match(main,/function AuditExplorer\(/);
 assert.match(main,/Refresh loaded Audit page/);
 assert.match(main,/Review related Audit/);
 for(const name of ["uxb-policy-filter-chips.ts","uxb-policy-table-ai-mapping.tsx",
  "uxb-policy-table-display.ts","uxb-policy-ai-reference-search.ts",
  "uxb-saved-views.tsx","uxb-saved-views-page.ts","uxb-audit-refresh.ts"]){
  if(name==="uxb-policy-ai-reference-search.ts")continue;// G27 search is in uxb-policy-expiry.ts
  assert.ok(existsSync(join(web,"src",name)),name);
 }
 assert.match(src("uxb-policy-expiry.ts"),/AI_SEARCH_FIELDS/);
 assert.match(src("uxb-saved-views.tsx"),/activeSavedViewFilterChips/);
 assert.match(main,/AdministrationHub/);
});

test("UI-06 source uses approved distinct requester/reviewer Core flow and keeps same-actor access advanced",()=>{
 assert.match(matrix,/UI-06 two-person/);
 assert.match(matrix,/SOURCE IMPLEMENTED \/ DEPLOYED TWO-USER PROOF OPEN/);
 assert.match(main,/TemporaryAccessRequestsPanel api=\{api\} operator=\{operator\}/);
 assert.match(main,/Advanced · direct Temporary Access/);
 for(const route of ["temporary-access-requests","review","revoke"])assert.ok(ui06.includes(route),route);
 assert.match(ui06,/Read Only can inspect policy state but cannot request, review, or revoke Temporary Access/);
 assert.match(ui06,/Request history/);
 const start=main.indexOf("function TemporaryAccessPanel(){");
 const end=main.indexOf("function PolicySafetyPanel(",start);
 assert.ok(start>0&&end>start);
 const single=main.slice(start,end);
 assert.match(single,/not a requester\/reviewer approval/);
 assert.match(single,/\/api\/v1\/temporary-access\/preview/);
 assert.match(single,/\/api\/v1\/temporary-access\/apply/);
 assert.match(matrix,/two-user deployed Browser proof|DEPLOYED TWO-USER PROOF OPEN/);
});

test("Old proposed audits point to current applied status instead of falsely claiming unfinished selected source",()=>{
 assert.match(md("WEB_UX_COMPETITIVE_AUDIT_2026-10.md"),/COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md/);
 assert.match(md("WEB_USER_JOURNEY_UX_ROADMAP.md"),/COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md/);
 assert.match(matrix,/M2 Core\/Agent integration/);
 assert.match(matrix,/M3 backup\/offline upgrade/);
 assert.match(matrix,/not all implemented/i);
});
