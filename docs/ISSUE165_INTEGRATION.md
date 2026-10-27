# Issue 165 unified source candidate

This is a source integration candidate, not a release or installed-product
acceptance result. The concurrent CLI100 actor continues its frozen candidate;
its scenario results must not be relabeled as results for this branch.

## Pinned inputs

| Source | Included revision | Purpose |
| --- | --- | --- |
| PR 220 | `4c508b2c75409d11b501897e97dc9bd428ed2f85` | CLI100 lifecycle, reservations, management-body streaming, restore revision and runtime-proof fixes |
| PR 221 | `2b1552111793e13f93abfcaa0cffed63b9d2a860` | Explicit operator-consent and PKCE identity handling; included through PR 222 |
| PR 222 | `d730c31c8f3ad37d40dbf080e3069a046c05dcb6` | Owner CLI, signed LAN references and compact onboarding foundation |
| PR 225 | `61bd826eb4bae9c8f727be41493ec4e98cc9b9e4` | DNS-optional pinned-CA IP bootstrap, early guided preflight and native SHA256 fallback |
| PR 226 | `cbbfebdafedd61e3eb91a0d9584a70cce9f3eb2d` | Missing-renderer fail-closed bounds and actual runtime target drift diagnostics |

The previously uncommitted authenticated legacy LAN-seed recovery is included
with its original regression tests. Original source worktrees and dirty changes
remain preserved; integration is not an instruction to overwrite another actor.
PR 224's separate native MCP deployment and the v3/Foundation feature lanes are
outside this integration's scope.

## Merge-specific invariants

- Server and Agent share the canonical enrollment target naming function and
  the existing 24-hex suffix. Existing IPv6 destination-object semantics remain.
- Public DNS launchers keep the 200/500 character bounds. Pinned-CA numeric-IP
  launchers retain their distinct 900/1500 bounds. Missing renderers/credentials
  never silently fall back to the advanced long package.
- Signed per-service recovery only changes untouched enrollment seeds whose
  endpoint, Service Object and Network Object agree with authenticated Server
  data. Operator changes and concurrent edits remain protected.
- A changed target clears old runtime proof and requires a fresh apply/ACK.
  Ordinary healthy heartbeats retain the PR 220 no-unnecessary-restart behavior.
- Legacy package/redeem regression cases explicitly select `--long-bootstrap`;
  the default remains a compact `/i/` command. Tests must not demand the retired
  extra SSH-login prompts from the backend.

## Qualification boundary

Focused regressions and the exact-HEAD Fast PR/artifact checks qualify the
source integration only. Native installation, full CLI100/Full User116, remaining
open findings and release gates retain their independent status. Do not merge to
main, deploy to an active E2E cohort, grant credentials, or release by inference
from this document.
