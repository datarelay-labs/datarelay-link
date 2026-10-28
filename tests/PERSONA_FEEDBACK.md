# Early user-persona defect feedback (development only)

This is a **regression backstop**, not another release gate. User-visible failures
discovered by ChatGPT while directly operating the real CLI are mapped to fast
deterministic regressions so similar bugs can be found before the next final E2E.

## Required separation

1. Before a named CLI Feature/Scenario or Full User E2E run, read its **entire
   exact-HEAD canonical test contract**. Do not replace that step with this file.
2. ChatGPT executes the public CLI as the User/Operator/Admin persona, following
   the current contract; source/test scripts are not the user's command oracle.
3. Preserve the real CLI transcript, runtime/result observations, run ID, candidate
   SHA, discovered defects, and required cleanup in the canonical run evidence.
4. After the complete discovery run is frozen and offboarded, fix findings in
   bounded batches. Add/identify focused regression tests for actual defects.
5. Record only the user goal, observed failure, canonical scenario and exact
   regression test method in `tests/persona-regression-links.json`.
6. Re-run the real **affected** user journey after each remediation batch. For
   final release quality, do a **fresh complete** contract-led human E2E run
   on the required unchanged candidate. Never convert scripted PASS into user PASS.

## Deterministic review of one frozen historical ledger

```bash
python3 tests/test_persona_findings.py
python3 tools/persona_findings.py
python3 tools/persona_findings.py \
  --ledger /absolute/path/to/frozen/run/ledger/findings.tsv \
  --run-id 20261007T064736Z-codex \
  --strict-findings
```

The tool validates that registered regression **methods exist** and reports open
findings without links. It does **not** execute user actions, prove that the
regression is sufficient, or authorize an E2E/release PASS. A missing link is a
development feedback gap, not a finding that may be silently waived.
