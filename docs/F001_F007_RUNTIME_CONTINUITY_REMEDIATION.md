# DRLink 2.4 — F001/F007 runtime continuity remediation boundary

**Source:** frozen Codex Full User E2E `codex-reviewed-20261010T085035Z`, actionable `F001` and `F007`. This is **ChatGPT engineering analysis**, not a substitute for the black-box operator's findings, not full E2E evidence, and not authorization to change shared/production configuration.

## Verified from source and deterministic regression

- `lib/drlink_v24_runtime.py::apply_agent_runtime` rebuilds `frpc.toml` from canonical Remote Services. Before commit `df101fbf`, any difference between the full JSON client-state and the generated state forced a **complete `drlink-client` FRP restart even when the actual rendered proxy TOML and verified runtime generation were unchanged**.
- Dedicated test `test_F001_F007_same_proxy_config_metadata_delta_does_not_restart_frpc` failed on old code (unwanted reapply) and passed after `df101fbf`. It also proves unverified generation and explicit `force_reapply` still cause reapplication; with genuine current-generation evidence, an explicit metadata-only Agent `system synchronize` preserves healthy state and does not restart.
- Scoped runtime allocator, status parity, bootstrap, distributed atomicity and procedure tests passed. This removes a genuine unnecessary restart path but **DOES NOT close F001 or F007 overall**. An actual Fixed TCP enable/disable changes the rendered proxy list, so the default implementation still performs a full FRP restart and may interrupt unrelated HTTP/TCP services.
- F001's historical `Synchronization DEGRADED` vs later `show remote-service ssh HEALTHY` needs same-provenance live generation/Agent+Server ACK correlation. One real SSH success does not prove that every configured proxy exists in the verified **current** FRP connection epoch. Do **NOT** fake a HEALTHY response based on reachability alone.

## Required zero-collateral-change design (must be approved before implementation/deployment)

1. Analyze and review FRP's documented dynamic client proxy reload. The upstream FRP client docs describe `frpc reload -c ./frpc.toml` but require a local `webServer` control API. The current DRLink renderer does **not** create this endpoint. Source: https://gofrp.org/en/docs/features/common/client/.
2. A reload implementation must not silently open a control listener or introduce an unauthenticated HTTP API. Require a separately reviewed, loopback-only, authenticated, least-privilege admin endpoint; protect credentials and file modes, allow an existing approved runtime owner to initiate changes only, and never bypass any previous authorization denial.
3. Ensure a staged new-frpc configuration is validated without exposing secrets. Require deterministic Service Object/Remote Service/port ownership, fresh signed Agent/Server management ACK and **new/current proxy registration evidence**. Existing unchanged proxies and established client connections must retain continuity; a successful `frpc reload` exit code alone is **not** enough.
4. On failure to authenticate/reload/verify, fail closed, preserve the previous effective configuration when possible, expose `PARTIAL/RECOVERY_REQUIRED` with next public diagnostics, and avoid an unannounced full restart of other published services. Do not claim that a rollback is complete until the public paths and receiver-confirmed effects are rechecked.
5. Independent negative checks must cover: missing/revoked admin auth, stale and mismatched Source HEAD, partial Server enrollment, old vs new generation logs, race with connection/restart, disabled/re-enabled Fixed TCP 3 rounds, unchanged SSH/HTTP/HTTPS/TCP traffic and UDP rejects, port allocation and leave-safe semantics, Linux native and separately authorized Windows/Rocky routes.
6. Performance acceptance in a **dedicated legitimate disposable lab**: warm up the same frozen source, record stable baseline, then command-stamped Fixed TCP mutations at realistic load and continuously probe unrelated unchanged endpoints (F007). Keep high 64-worker saturation separated from low-rate lifecycle collisions. Distinguish intentional Fixed endpoint denial from collateral reset; both count honestly. Record initial/final PIDs, current-generation proxy status, immutable artifact IDs and timestamps.
7. If a secure local admin listener/operation cannot receive legitimate approval or no safe proof is possible, F007 remains OPEN, dependent release quality gates remain blocked and there is **no** Full User E2E or CLI-FCS PASS claim. Implementer is CHATGPT_CHAT; Codex is tests only when expressly dispatched after remediation and lab GO.

## Handoff state

- `F001=PARTIALLY_MITIGATED; CURRENT_GENERATION_LIVE_RETEST_REQUIRED`
- `F007=PARTIALLY_MITIGATED_FOR_METADATA_ONLY; DYNAMIC_PROXY_CHANGES_OPEN`
- `PASS1=0`, `PASS2=0`, `RELEASE=HOLD`.
