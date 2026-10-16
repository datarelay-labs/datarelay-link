#!/usr/bin/env python3
"""Derive the independent CLI-only functional contract from the canonical 116-ID Full User E2E.

This generator deliberately preserves every non-AI/MCP original scenario body,
including negative, concurrency, lifecycle and performance criteria.  Only the
explicit seven core AI/MCP scenarios plus the nine X/Plugin scenarios are omitted.
Mixed scenarios have narrow documented substep excisions.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/FULL_USER_E2E_SCENARIOS.md"
OUTPUT = ROOT / "docs/CLI_ONLY_E2E_SCENARIOS.md"
EXCLUDED = {
    "U-007", "U-011", "O-013", "O-014", "A-006", "C-006", "P-011",
    "X-001", "X-002", "X-003", "X-004", "X-005", "X-007",
    "X-008", "X-009", "X-010",
}
MIXED = {
    "U-009", "U-013", "A-004", "A-007", "A-009", "A-011",
    "A-012", "A-016", "S-017", "S-024", "C-015", "P-023", "P-024",
}
ID_PATTERN = re.compile(r"^## ((?:U|O|A|S|C|P)-\d{3})\s+[—:-]\s+(.+)$", re.M)
BLOCKED_TERMS = re.compile(
    r"\b(?:AI Identity|AI Access|AI-assisted|AI adviser|AI mirror|"
    r"ChatGPT|Plugin|MCP|OAuth|AI one-shot|AI workflow)\b", re.I
)

INTRO = """# Data Relay Link v2.4.0 — CLI-only Full Functional E2E (100 scenarios)

> **Status:** Independent, executable CLI-only user test contract. **Not** Full User E2E / MCP / AI qualification.
> **Source:** `docs/FULL_USER_E2E_SCENARIOS.md` (all 116 original IDs and headings preserved in its canonical document).
> **Product baseline:** v2.4.0 **includes** AI Access and MCP Bridge; they are excluded **only from this test profile**, not removed from the product.
> **Executor:** current owner-selected runtime (default `CHATGPT_CHAT`); current explicit instruction overrides historical Codex-only text.
> **Generation:** `python3 tools/generate_cli_only_e2e_contract.py --write`; `--check` verifies no source drift.
> **Safety:** preserve current authorization, exact live platform/tool refusals, other actors, host ownership and management access; never reroute a denied effect.
> **Candidate:** do not infer installed Source HEAD from a Git checkout; record each installed Server/Agent's provenance.

## 1. Scope and complete original-ID traceability

- **Canonical parent:** 116 scenarios (13 U, 15 O, 20 A, 20 S, 15 C, 24 P, 9 X).
- **CLI-only:** 100 retained original IDs, including mixed IDs with only the specifically excluded AI/MCP substeps removed.
- **Excluded AI/MCP-only:** U-007, U-011, O-013, O-014, A-006, C-006, P-011, X-001, X-002, X-003, X-004, X-005, X-007, X-008, X-009, X-010. Record `EXCLUDED_AI_MCP`, **never PASS**.
- **Mixed IDs, non-AI parts mandatory:** U-009, U-013, A-004, A-007, A-009, A-011, A-012, A-016, S-017, S-024, C-015, P-023, P-024.
- The existing `tools/cli_only_e2e_inventory.py` is the authoritative 116-ID ledger initializer. Every scenario heading and applicable requirement from the parent is retained below, not only linked indirectly. The precise excluded substeps are described at the affected headings; no other steps may be excused for being in a mixed ID.
- Direct CLI, help/`?`, menu, REPL, Tab and wizard UX, installers/upgrade/uninstall, configuration bundle, Remote/Internet Access, real SSH/SCP/HTTP/HTTPS/TCP, proxy application traffic, host lifecycles, policy ALLOW/DENY, failure/recovery, all available-host concurrency and real performance remain in scope.
- Each direct-user PASS needs **actual public** drlink command, observed effects, truthful exit codes and full evidence. CLI-only evidence never grants full 116-scenario User E2E PASS or a v2.4.0 release gate. Full User E2E still requires genuine AI/MCP tests, full release gates and two complete same-HEAD passes.

## 2. Start eligibility: no global test-start gate

1. Resolve `datarelay-labs/datarelay-link`, read `AGENTS.md`, `.engineering/project.yaml`, current installed candidate identities and this entire executable contract before the first user action.
2. Inspect branch/HEAD/dirty status, active owners and existing RUN_ID/processes **once**. Do not start a competing actor, repin its candidate, edit its owned state or replace its evidence. Use independent safe resources/hosts. A live actor owns only its own mutable scope, not the entire lab.
3. **There is no global LAB_GO** or `phase-state.json`, universal host-GO, AI/MCP/OAuth readiness, FCS completion, whole CI wait, newly created VM/snapshot or repeated owner permission required to begin an independently runnable CLI scenario.
4. Dirty worktree: never build a falsely qualified candidate from uncommitted source. Continue public CLI observations against a truthfully pinned existing installation, with its actual `INSTALLED_HEAD`; only exact matching candidate evidence may become candidate PASS.
5. Missing prerequisite blocks only the dependent action. `ENVIRONMENT_BLOCKER` must mean demonstrated host/topology/required external resource unavailability, not a personal preference, stale report, absent release SLO or unstarted setup work.
6. Historical platform/tool refusal is **evidence to re-check under present policy**, not a permanent ban. An actual current denial remains binding for that **exact operation**: do not bypass it by changing executor, sandbox, host, command, identity, permissions or route. Record tool, host, attempted command, literal error and impact, continue independent checks. High-risk production/credential/permission/release effects still need their own authority.
7. Separate the functional Server (`frp-e2e-server`) from the owner-assigned public DNS/hostname Server (`frp-release-server`) when applicable. Ordinary CLI, lifecycle, traffic, concurrency and performance use the functional Server; public hostname/DNS-specific substeps use the approved DNS target. Missing DNS affects only those substeps.
8. All claims require **actual public CLI actions** through `drlink`; helper scripts can orchestrate/measure/record but cannot replace a user-role discovery path, a real confirmation or actual application traffic. Every per-host prerequisite and effect must be observed directly. Interactive PTY/TTY is required **only for an operation whose public CLI contract needs it**; a failed TTY tool blocks its interactive criterion alone. Do not turn CI, source inspection or scripted PASS into user E2E PASS.

## 3. Per-run state, ownership, lifecycle and evidence

- Generate one private persistent `RUN_ID` directory outside `/tmp`, mode 0700; secret-bearing evidence mode 0600. Initialize **116 original ledger rows** (100 CLI-only + 16 exclusions) using:

  `python3 tools/cli_only_e2e_inventory.py init --run-root <PRIVATE_RUN_ID> --source-head <FULL_40_CHARACTER_GIT_SHA>`

- Record per action `RUN_ID`, scenario/substep/repeat, actual host and role, Source/Installed HEAD, public exact command, stdout/stderr (redacted), exit code, UTC start/end, observed service/traffic effect, SHA256 of receiver payload if applicable, and run-owned cleanup result.
- Before each host's first **mutating** CLI test, inventory previous actors' immutable evidence and resources. Clean **only resources of the current run or expressly disposable test-owned resources**, via documented public lifecycle paths. Do not delete other worker resources, customer data, management tunnels/SSH, preserved previous-run evidence, or globally reset a host merely to obtain a label. If a clean-install scenario really requires a clean host, use an independently owner-authorized disposable host; inability to obtain it blocks **that** fresh-install scenario, not all existing-installed behavior.
- Preserve persistent client identity, Service IDs, allocated public ports, security policy and rollback state according to each scenario. Include genuine negative tests and recovery; valid pre-existing tests are not repeated merely for different ledger IDs when direct same-run evidence legitimately satisfies both.
- When a candidate mismatch exists, record stale runtime as correlation only. After fixes freeze old evidence; install a new immutable qualified candidate on a separately authorized host and re-run affected conditions at its exact HEAD.
- Any currently denied Functional Server uninstall (historically B014) or other high-risk native effect must be re-evaluated on the **same authorized tool/target under current policy**. If the current attempt is denied, retain the precise denial and leave only the dependent test blocked; never alter route or use an alternative actor to defeat it.

## 4. Real topology, timing and performance

- Run real User, Operator, Administrator, Incident Responder and Platform Maintainer missions through the visible CLI. Vary fresh/existing/stale state, command order, direct/REPL/wizard presentation, selector/role/negative input, previous failed mutation, and recovery wherever applicable. Capture genuine public `drlink` behavior before looking at implementation.
- Use actual suitable Linux/Windows/macOS Agent and target hosts where present; preserve native OS and all-host limitation receipts. Do not require hypothetical host tiers or an unrelated extra VM.
- Functional load requires **60-second warmup**, **300-second steady state for every applicable case**, and **P-013 3,600-second functional soak** once representative real application data paths work. **P-019 8h/24h is optional until explicitly selected.**
- Exact labels retained for machine audit: `WARMUP=60s`, `STEADY_STATE_EACH_CASE=300s`, `SOAK=3600s`, `EXTENDED_SOAK=8h`, `ENDURANCE_SOAK=24h`; only the last two require explicit selection.
- Run independent persistent workloads via managed `tmux`/systemd/equivalent when a connection cannot guarantee process lifetime. Retain PID/session, start/end UTC, real 60/300/3600-second samples and terminal results; do not claim elapsed PASS from an active PID or timer.
- Measure receiver-confirmed 1KiB/64KiB/1MiB and stream/full-duplex goodput, checksum, CPS, 4/16/64+ connections, p50/p95/p99 latency, CPU/RSS/FD, mixed applications, denied traffic, saturation and function-under-load collision/recovery. Apply existing approved numeric SLOs without weakening them. **Unknown numeric SLO** is `MEASURED_NOT_QUALIFIED` for numeric qualification only, never justification to skip runnable functional measurements or hide actual errors.

## 5. Dispositions and truthfully separate completion gates

Allowed outcomes: `NOT_RUN`, `IN_PROGRESS`, `PASS`, `FAIL`, `PARTIAL`, `FAIL_PRECONDITION`, `BLOCKED_ENVIRONMENT`, `BLOCKED_TOOLING`, `BLOCKED_PLATFORM_DENIAL`, `BLOCKED_MANAGEMENT_PATH`, `MEASURED_NOT_QUALIFIED`, `EXCLUDED_AI_MCP`; `P-019` may remain `NOT_RUN` when unselected. Always distinguish `BLOCKED` vs `FAIL`, the product cause vs management/tool limitations, candidate qualification vs valid installed-version behavior, functional PASS vs unqualified numeric SLO.

- `EXECUTABLE_SCOPE_COMPLETE`: every safe runnable original CLI-only criterion has a supported result or a concrete, attributable dependency-specific blocking record. No missing substeps hiding behind a completed parent row.
- `ALL_APPLICABLE_CLI_E2E_PASS`: every required CLI-only criterion and its native/traffic/performance conditions is qualified PASS on the exact candidate, with no unresolved mandatory defect or blocker. Optional profiles are identified separately.
- Neither status implies `FULL_USER_E2E_PASS`, AI/MCP acceptance, a production deployment, a release, merge/tag or owner acceptance.
- A tool or platform failure should be attempted/recorded as a bounded concrete operation and **must not be inflated into a global blocker**. Close out run-owned resources via public paths and report which original IDs remain FAIL/PARTIAL/BLOCKED/NOT_RUN.

## 6. Non-AI/MCP scenario matrix: exact preserved original requirements

The following bodies are extracted from the current canonical Full User E2E. They retain original IDs, titles, assertions, negative/recovery/performance requirements and order, except explicit AI/MCP-only scenarios/substeps. Headings in the source remain authoritative; if the source changes, regenerate and review the diff rather than silently using a stale copy.

"""

OUTRO = """# 15. CLI-only provenance and report

Retain the 116-row original-ID inventory and machine-readable ledger from
tools/cli_only_e2e_inventory.py. A qualified PASS requires actual matching
installed Source HEAD, direct user action/traffic evidence and verified cleanup.
Report all 100 CLI-only outcomes and 16 EXCLUDED_AI_MCP outcomes with true
substep, platform, performance and safety dispositions. This does not confer
Full User E2E PASS, AI/MCP acceptance or v2.4.0 release authority.

Refer to docs/CLI_ONLY_E2E_BLOCKER_AUDIT.md for a per-contract assessment of
real prerequisites versus artificial test-start restrictions.
"""


def patch_section(sid: str, text: str) -> str:
    """Only the explicit 13 mixed-parent exclusions; raises on any surviving AI/MCP steps."""
    if sid == "O-001":
        text = text.replace("system certificate status, ", "")
    elif sid == "U-013":
        text = re.sub(r"(?m)^- AI Identity authentication vs AI Access authorization ambiguity;\n", "", text)
        text = text.replace("AI_TERM=", "PUBLIC_TERM=")
        text = text.replace("If ChatGPT must guess hidden syntax", "If an operator must guess hidden syntax")
        text = text.replace("and AI-assisted", "and direct-user")
        text = text.replace("AI-assisted", "direct CLI")
    elif sid == "A-004":
        text = text.replace("Internet Access and AI Access reset", "Internet Access reset")
    elif sid == "A-007":
        text = text.replace("Service Group, Permission Object/Group, AI Identity, and referenced Managed Host",
                            "Service Group, and referenced Managed Host")
    elif sid == "A-009":
        text = re.sub(r"(?m)^- AI identity metadata and authentication configuration status;\n", "", text)
    elif sid == "A-011":
        text = "\n".join(line for line in text.split("\n") if not re.match(
            r"^(?:system diagnostics mcp|system certificate (?:status|preflight|issue|renew|import).*)$", line.strip()
        ))
        text = re.sub(r",? MCP diagnostics are actionable,?", ",", text)
        text = re.sub(
            r"(?m)^Certificate issue/renew/import operations must be exercised[^\n]*\n", "", text
        )
        text = text.replace(", certificate lifecycle state is coherent", "")
    elif sid == "A-016":
        text = text.replace("## A-016 — AI workflow and CLI traceability audit",
                            "## A-016 — Direct CLI workflow and traceability audit")
        text = text.replace("At the end of FULL_USER_E2E", "At the end of CLI_ONLY_E2E")
        text = re.sub(r"(?m)^-> AI_ASSISTED_RESULT/EVIDENCE\n", "", text)
        text = text.replace(
            " and one AI-assisted use-case record unless an explicit permitted AI_NOT_APPLICABLE reason is retained",
            ""
        )
        text = re.sub(r"(?m)^- (?:AI Identity/AI Access|AI one-shot|cross-context AI request|Export -> AI -> Reapply);\n", "", text)
    elif sid == "S-024":
        text = text.replace("and/or AI assistance grounded in user-visible output", "grounded in user-visible output")
    elif sid == "C-015":
        text = text.replace("AI-assisted, and isolated-load lanes", "isolated-load lanes")
        text = text.replace("AI-assisted", "direct CLI")
    elif sid == "P-023":
        text = text.replace(" AI/MCP stress elements remain gated on the functional MCP prerequisite.", "")
        text = re.sub(r"(?m)^- concurrent AI/MCP requests including allowed and denied operations;\n", "", text)
        text = text.replace("Remote/Internet/AI Access policy reads", "Remote/Internet Access policy reads")
        text = re.sub(r"(?m)^MAX_STRESS_AI_MCP_CONCURRENCY=\n", "", text)
    elif sid == "P-024":
        text = text.replace("AI_ASSISTED_CONTROL_OPERATION_ON_ISOLATED_STATE", "DIRECT_CLI_CONTROL_OPERATION_ON_ISOLATED_STATE")
    text = text.replace("CLI/AI Master", "current v2.4.0 CLI Reference")
    if sid in MIXED:
        remaining = [(i + 1, line.strip()[:145]) for i,line in enumerate(text.splitlines())
                     if BLOCKED_TERMS.search(line)]
        if remaining:
            raise AssertionError(f"{sid} still has AI/MCP-only wording: {remaining}")
    return text


# Preserve all original 13/14 platform, topology, direct CLI commands, and
# corresponding criteria; omit only commands solely dedicated to AI/MCP.
AI_ONLY_CLI_COMMAND = re.compile(
    r"^(?:show|set|unset) (?:ai-|permission-|mcp-tls)"
    r"|^test ai-access\b|^system diagnostics mcp$"
    r"|^system certificate (?:status|preflight|issue|renew|import)\b"
    r"|^system credential (?:rotate|revoke|configure|approve-oauth|deny-oauth)\b"
    r"|^supported AI/MCP client when applicable$", re.I
)

def platform_and_command_matrix(source: str) -> str:
    a = source.index("# 13. Platform matrix")
    b = source.index("# 15. Conditional ChatGPT Plugin / MCP relay integration lane")
    lines = [line for line in source[a:b].splitlines()
             if not AI_ONLY_CLI_COMMAND.match(line.strip())]
    result = "\n".join(lines).replace("FULL_USER_E2E", "CLI_ONLY_E2E")
    result = result.replace("public v2.4 CLI/AI Master", "public v2.4.0 direct CLI Reference")
    if re.search(r"(?mi)^(?:show|set|unset|test) (?:ai-|mcp-tls|permission-)", result):
        raise AssertionError("AI/MCP command leaked into direct CLI inventory")
    return result.rstrip() + "\n\n"

def original_shared_execution_contract(source: str) -> str:
    """Retain referenced original repetition, deliberate-mistake and stop rules."""
    a = source.index("### 1.3.2 Mandatory repetition and sequence-permutation contract")
    b = source.index("### Dimension A — Direct CLI role operation")
    rep = source[a:b]
    rep = rep.replace("FULL_USER_E2E", "CLI_ONLY_E2E")
    rep = rep.replace(
        "AI_HIGH_RISK_WORKFLOW_MIRROR=AT_LEAST_2_EQUIVALENT_STARTING_STATES_WHERE_APPLICABLE\n", ""
    )
    rep = rep.replace("Direct/AI execution", "Direct CLI execution")
    rep = rep.replace(
        "They may use only the installed product's public UX plus AI assistance grounded in the same user-visible information.",
        "They may use only the installed product's public UX; this direct-only profile does not include an AI Adviser."
    )
    rep = rep.replace("CLI/AI Master", "private CLI Master")
    rep = rep.replace("AI_INPUT_DEFAULT=NATURAL_LANGUAGE_GOAL_PLUS_USER_VISIBLE_CLI_OUTPUT_ONLY\n", "")
    rep = rep.replace("wrong AI permission, ", "")
    rep = rep.replace("and/or AI assistance using only user-visible output", "using only user-visible output")
    rep = rep.replace("RECOVERY_USING_ONLY_CLI_OR_AI=100%", "RECOVERY_USING_ONLY_CLI=100%")
    a = source.index("### 1.4.1 Scenario prerequisites, evidence reuse, and bounded stop rules")
    b = source.index("## 1.5 Parallel execution scheduler")
    pre = source[a:b].replace("functional MCP/auth, ", "")
    pre = pre.replace("FULL_USER_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL",
                      "CLI_ONLY_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL_NO_AI_MCP")
    return "### Preserved original shared execution criteria\n\n" + rep.strip() + "\n\n" + pre.strip() + "\n\n"

def render() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    a = source.index("# 7. User scenarios")
    b = source.index("# 13. Platform matrix")
    core = source[a:b]
    matches = list(ID_PATTERN.finditer(core))
    if len(matches) != 107:
        raise AssertionError(f"expected 107 original U/O/A/S/C/P scenario IDs, got {len(matches)}")
    blocks = [core[:matches[0].start()]]
    kept = []
    for i, match in enumerate(matches):
        sid = match.group(1)
        block = core[match.start():matches[i+1].start() if i+1 < len(matches) else len(core)]
        if sid in EXCLUDED:
            # Retain any next major group heading at the tail of an excluded block.
            assert not re.search(r"(?m)^# (?:8|9|10|11|12)\. ", block), sid
            continue
        kept.append(sid)
        blocks.append(patch_section(sid, block))
    if len(kept) != 100 or len(set(kept)) != 100:
        raise AssertionError(f"expected 100 CLI-only scenarios, got {len(kept)}")
    if not MIXED.issubset(kept):
        raise AssertionError("mixed scenario omitted")
    all_content = INTRO + original_shared_execution_contract(source) + "\n".join(blocks) + "\n" + platform_and_command_matrix(source) + OUTRO
    signature = hashlib.sha256(source.encode()).hexdigest()
    all_content = all_content.replace(
        "> **Generation:** ", f"> **Canonical Full User E2E SHA256:** `{signature}`\n> **Generation:** ", 1
    )
    detected = ID_PATTERN.findall(all_content)
    if len(detected) != 100:
        raise AssertionError("rendered count mismatch")
    return all_content.rstrip() + "\n"

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    expected = render()
    if args.write:
        OUTPUT.write_text(expected, encoding="utf-8")
        print(f"wrote {OUTPUT} ({len(expected.splitlines())} lines)")
    elif args.check:
        actual = OUTPUT.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit("CLI_ONLY_E2E_SCENARIOS.md is stale or manually divergent; run --write and inspect diff")
        print("CLI_ONLY_CONTRACT_PARITY=PASS; ORIGINAL_IDS=116; CLI_IDS=100; EXCLUDED_AI_MCP=16")
    else:
        p.error("select --write or --check")

if __name__ == "__main__":
    main()
