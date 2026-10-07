# RETIRED — OCI Acceptance Plan

> **Status:** Retired historical document.
> **Historical scope:** v2.1.1-era operator acceptance.
> **Current qualification authority:** `FULL_USER_E2E_SCENARIOS.md`, `RELEASE_VALIDATION.md`, and `RELEASE_CHECKLIST.md`.

This file is intentionally retained only as a tombstone because older scripts, tests, and links still reference its path.

Its former command examples and workflow instructions were removed because they used obsolete public CLI forms and must not be used for current Data Relay Link behavior, testing, documentation, or release decisions.

For current v2.4 CLI truth use, in order:

1. exact candidate runtime `drlink help commands`;
2. `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`;
3. `CLI_REFERENCE.md`;
4. `Data Relay Link CLI Information Architecture.md` for guided navigation only.

Current direct grammar is:

```text
drlink <ACTION> <RESOURCE> [TARGET] [VALUE]

show
set
unset
test
system

menu
help
exit
```

Do not recover or reconstruct retired pre-v2.4 direct-command examples from Git history for current use.

Historical Git history remains available only when explicitly investigating an old release.
