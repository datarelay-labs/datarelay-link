# Data Relay Link UI Redesign — Five-Novice Usability Protocol

Status: READY TO RUN / ZERO PARTICIPANTS RECORDED

This is the predeclared UXR-7.6 protocol. It prevents retrospective success criteria changes and prohibits generated or fake participants.

## Candidate freeze

Every participant must use the same exact deployed candidate HEAD and the same seeded test state. Record the candidate before Participant 1. If source or seeded state changes because of a product fix, restart the five-person batch.

Do not expose implementation notes, raw route IDs, menu answers or expected click paths before the participant attempts a task.

## Participant eligibility

Each participant must:

- be a real human independent of the implementation session;
- not have authored or reviewed the UI change being measured;
- be unfamiliar enough with the redesigned UI that discovery is meaningful;
- use their own permitted test session;
- receive no product credentials through Git history, screenshots, chat logs, or this committed ledger.

Record only a pseudonymous participant label. Do not commit names, email, credentials, IP addresses, session identifiers, or screenshots containing private data.

## Five required tasks

Run in this order unless a task is legitimately unavailable to that role.

### T1 — Find the next safe action

Starting at Home, ask: You need to connect one internal service. Show where you would start.

Measure time until the participant identifies the correct primary next action.

Predeclared discovery target: 10 seconds.
Pass threshold: at least 4 of 5 participants find it within 10 seconds.

### T2 — Find a pending server review

Provide a seeded pending-approval Agent. Ask: Find the server that still needs review and show what you would inspect before approving it.

Participant must not be given a raw Host ID.

### T3 — Publish one service

Provide an already approved and connected test Agent. Ask: Publish one narrow SSH service from this server, stopping before any unsafe or destructive confirmation you do not understand.

Measure menu changes, wrong screens, raw-ID copying, assistance and whether the participant distinguishes queued/configured from reachable.

### T4 — Explain access

Provide a seeded source, destination and Service Object with an authoritative Core decision. Ask: Find out why this access is allowed or denied.

Participant must distinguish policy decision from transport/live-use evidence and must not treat UNKNOWN as DENY or success.

### T5 — Return from Activity

Start from one selected resource's Activity context. Ask: Inspect this event, then return to the resource you were investigating.

Participant must return without manually transferring a resource ID.

## Measurements

For every task record:

- completion: PASS / FAIL / NOT_SUPPORTED
- discovery_seconds
- total_clicks
- wrong_menu_count
- raw_id_transfer: YES / NO
- unprompted_assistance: YES / NO
- misleading_success_observed: YES / NO
- participant_note: bounded plain text without private identifiers
- observer_finding: NONE / P0 / P1 / P2-USER-BLOCKING / NONBLOCKING

Timing starts when the task statement ends and stops when the participant identifies the requested target/action. Do not stop or restart the timer because the participant opens a wrong menu.

## Overall pass

UXR-7.6 passes only when:

- five valid independent participants completed the batch on the same frozen candidate;
- all applicable tasks complete without raw-ID transfer and without unprompted assistance;
- at least 4 of 5 meet the 10-second T1 discovery target;
- every P0/P1/P2-USER-BLOCKING finding is fixed and the affected real task is rerun;
- retained evidence remains privacy-safe.

## Empty execution ledger

| Participant | Candidate HEAD | Task | Completion | Discovery seconds | Clicks | Wrong menus | Raw ID transfer | Assistance | Misleading success | Finding | Retest |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| P1 | NOT_RUN | T1–T5 | NOT_RUN | — | — | — | — | — | — | UNASSESSED | NOT_RUN |
| P2 | NOT_RUN | T1–T5 | NOT_RUN | — | — | — | — | — | — | UNASSESSED | NOT_RUN |
| P3 | NOT_RUN | T1–T5 | NOT_RUN | — | — | — | — | — | — | UNASSESSED | NOT_RUN |
| P4 | NOT_RUN | T1–T5 | NOT_RUN | — | — | — | — | — | — | UNASSESSED | NOT_RUN |
| P5 | NOT_RUN | T1–T5 | NOT_RUN | — | — | — | — | — | — | UNASSESSED | NOT_RUN |

No row may be changed to PASS from synthetic Browser, CI, screenshots, LLM simulation or a second run by the same person.
