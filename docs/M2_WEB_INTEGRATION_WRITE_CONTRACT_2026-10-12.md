# DRLink M2 — Core/Web integration write-receipt qualification (2026-10-12 KST)

## Exact scope and source authority

- **Roadmap:** [GitHub Issue #184](https://github.com/datarelay-labs/datarelay-link/issues/184), ACTIVE Work Packet #182. M1 applicable competitor UI findings G01–G37 already source-mapped and source-tested on Draft PR #206; owner explicitly defers real User E2E. This document describes the **next independently executable M2 implementation**, not another competitor-Gap loop, merge/release authorization or an alternate security authority.
- **Product Web** `web/src/main.tsx::IntegrationsPanel`, `web/src/uxb-integration-write-receipts.ts`; **Core code read-only for contract** `lib/drlink_web_service.py::write_api`, `lib/drlink_service_accounts.py::ServiceAccountStore.create/rotate/revoke`, and `lib/drlink_webhooks.py::WebhookStore.create/rotate_secret/disable`. All credentials are minted and authorized by Core; the product Web only displays structurally verified one-time responses.
- **Preservation:** isolated source worktree `pfci-m1-audit-accessibility-20261011`, existing Draft PR #206. Protected `v300-drl3-0` dirty `tests/test-v30-webhook-delivery.py`, PF11B six-file dirty connectivity source and PF9 separate dirty release artifacts were READ ONLY and remain unmodified. Do not cherry-pick/merge these overlapping Core/Web/release branches, alter Web/SSH privileges, signer, installed host or previously security-blocked tests.

## Reproduced product-level Core ↔ Web contract defect

Prior `IntegrationsPanel::mutate` regarded any successful POST response as sufficient for Copy once, taking `result.credential||result.secret` without verifying type, prefix, exact Core identity or credential reference. A malformed HTTP success could show an empty/unrelated one-time token; operator later cannot recover rotated material from the Core private inventory. Service Account and Webhook creation handlers then cleared their user-entered form even when `mutate` caught an error. `datetime-local` was converted by unguarded `new Date(...).toISOString()`, which throws/normalizes invalid manual local input. Busy-only guards could allow a subsequent create/rotate while a previous one-time secret was still visible.

**Real Core response contracts (read directly, no guessed endpoint):**

| Existing Web Core POST | Valid Core success response identity/effect | Original Web M2 acceptance |
| --- | --- | --- |
| `/api/v1/service-accounts` (create) | `id=msa_ + 24 lowercase hex`, `credential_id=msc_ + 24 lowercase hex`, `credential=drlink_sa_ + 43 urlsafe chars`, same normalized name | Show only a newly verified one-time token, ID bound to that returned account |
| `/api/v1/service-accounts/rotate` | `credential` and `credential_id` only; response deliberately **does not include account ID** | Bind token to explicitly requested `account_id` only after both fields validate; no guessed response ID |
| `/api/v1/webhooks` / `/api/v1/webhooks/rotate` | `id=wh_ + 24 lowercase hex`, `secret=drlink_wh_ + 43 urlsafe chars` | Bind rotate receipt to exactly requested webhook ID and verify secret format |
| `/api/v1/webhooks/disable`, `/api/v1/service-accounts/revoke` | `id` requested and explicit `enabled:false` | Never claim disabled/revoked from unverified 200, `0`, `false` string or mismatched ID |

## Independent source implementation / limits

- Pure `observedIntegrationWriteReceipt(path,body,result)` accepts only fixed existing Core operation names and explicitly verified public receipt structure. All others yield null. This is a **format/identity agreement**, NOT cryptographic proof, live credential redemption, network/Webhook delivery confirmation or authorization.
- `integrationLocalExpiryToUtc` accepts blank optional or strict, valid `YYYY-MM-DDTHH:mm` browser-local time (calendar and wall-clock roundtrip), creates an absolute ISO UTC instant, rejects impossible/normalized times before any Core write.
- The Web `mutate` **never** displays unverified secret, keeps entered create fields on a failed/unknown result, and warns that POST may have committed before a missing reply — inspect authorized Core inventory/Audit before attempting a new request. It refuses overlapping requests and any further write while the current one-time token awaits explicit **Done** dismissal; keeps existing Core Admin RBAC/CSRF and explicit revoke/disable confirmations.
- No new API, token storage, localStorage, display of nested Core response, permission, password or data egress; no vendor source. Core issuer remains sole authority. The one-time UI secret is shown to the authorized current browser operator only, exactly as prior UI scope.
- **Unverified:** installed Web/Core compatibility on an owner-approved real host, 3-role logged-in Browser, actual two-user E2E, production webhook delivery, permitted security reviews, CI merge/release gates.

## Actual focused and native QA

- First focused NEW test RED: missing `uxb-integration-write-receipts.ts` resulted in 1/1 failure. After original implementation new integration-receipt tests + existing integration-status suite **15/15 PASS** (six cases of structural/identity, bad secrets, local expiry, exact Web form preservation, a seventh concurrent/one-time lock source guard plus prior eight).
- Existing Core native baseline on clean candidate **before this source change**: Python Web Service **30/30**, Web Auth **12/12**, Web MFA **5/5**, Management Query **24/24**, Management Adapters **8/8** PASS (`/tmp/drlink-m2-source-baseline-8ODKMB`). They are **NOT** post-change installed/E2E evidence.
- Matching Core Store native existing contract tests were executed on new source tree: Service Account **3/3**, Webhook **3/3** PASS (`/tmp/drlink-m2-native-integration-zXcE7b`). The specifically protected Webhook *delivery* test was not executed.
- Final affected candidate native Web P0 **38/38 PASS**, Journey **357/357 PASS**, Administration **20/20 PASS**, Python UX **56/56 PASS**, offline Web Bundle **6/6 PASS**, production Web build and `git diff --check` PASS, log `/tmp/drlink-m2-integration-web-qa-bq8y4p`. This is NOT real E2E or owner security acceptance.
