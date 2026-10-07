# Data Relay Link — Installation

> **Status:** v2.4 development operator guide
> **Authority:** Product semantics are defined by `PRODUCT_MASTER.md` and the CLI/AI Master. Release provenance rules are defined by `VERSION_POLICY.md`.

## 1. Installation model

Data Relay Link has two runtime roles:

```text
DRLink Server
DRLink Agent Host
```

The Server is Linux-based. Agent Hosts are supported on the platforms qualified by the current release evidence.

The normal operator interface after installation is:

```bash
sudo drlink
```

## 2. Source identity before stable release

Until an immutable `v2.4.0` tag exists, do not install from a future tag, mutable `main`, or an unqualified `latest` path.

Development/pre-release installation uses an exact immutable Git SHA or an explicitly qualified candidate artifact.

Conceptual exact-SHA bootstrap:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/datarelay-labs/datarelay-link/<EXACT_SHA>/dist/bootstrap-server.sh \
  | sudo bash
```

The exact SHA must be the candidate or source-preparation HEAD that the operator intends to test.

Stable installation may use the immutable stable tag only after that tag and its qualified artifacts actually exist.

## 3. Server installation result

After installation, verify with read-only commands:

```text
system version
show status
system diagnostics
```

Expected identity includes:

```text
Data Relay Link product version
release channel
exact Source HEAD
Relay Engine (FRP) version
role = DRLink Server
```

A development build must not identify itself as stable.

## 4. Public identity and hostname

Server control/allocator identity and optional friendly hostnames are distinct.

```text
public_ip / public_host
→ control / allocator identity

public_hostname
→ optional published Remote Service alias

bootstrap_hostname
→ Zero-Touch bootstrap hostname
```

If installation allows a domain to be selected as the product public identity, that choice must be used consistently by generated bootstrap/Zero-Touch links and other user-facing URLs according to current implementation.

Changing a friendly Remote Service hostname alias must not silently change management identity.

### Internet Access listener recovery

The Internet Access listener address and port are **installer-owned** deployment
settings. They have no public `set server` command. Start with `system version`,
`system diagnostics`, and `show internet-access` to record the installed immutable
Source HEAD, current deployment mode, listener, and Server identity. Keep a
validated `system backup` before a planned reinstall and preserve the diagnostic
output before repairing an invalid listener.

Use the Server installer from the **same immutable release/source ref** as the
installed Server. From that verified release/source directory, the supported
installer invocation for a trusted address already assigned to the Server is:

```bash
sudo env FRP_EGRESS_LISTEN_ADDR=<TRUSTED_SERVER_ADDRESS> bash ./install-server.sh
```

If the port must also change, supply `FRP_EGRESS_LISTEN_PORT=<VALID_PORT>` in that
same installer invocation. The port must be 1–65535 and outside the Remote Service
range, Fixed TCP endpoint pool, and other infrastructure listeners. Preserve the
current `direct` or `single443` deployment mode and Server identity; this is not a
mode-switch or re-enrollment workflow. On an existing installation, omitted
listener settings retain their current values, so setting the address alone does
not request a new port. Use the normal install/reconfigure invocation shown above,
without `--upgrade`: the software-only upgrade path does not reconfigure this
listener. Do not edit `config.json` or derived runtime files by hand.

Review the installer's changes before proceeding. A reinstall can restart
services and interrupt active connections. Data Relay Link does not assign a new
OS interface address or change external firewall/NAT rules; those prerequisites
remain the operator's responsibility. Afterward, run `show internet-access` and
`system diagnostics`, and verify that protected applications still use the
intended proxy endpoint. A listener repair does not authorize additional policy
destinations or disable WHITELIST enforcement.

### Enrollment retention recovery

Enrollment retention is **installer-owned**; there is no public command to set
its stored configuration field. Normal Server installation configures the
supported default of **30 days** for retained terminal records. If diagnostics
reports an invalid retained value, first save the diagnostic evidence and
inspect `show enrollments`. The diagnostic scan uses 30 days for reporting but
does not repair configuration or delete records.

Use the Server installer from the **same immutable release/source ref** as the
installed Server. From the verified source directory, run the normal supported
reconfiguration with `sudo bash ./install-server.sh`, without `--upgrade`.
Preserve the current deployment mode, public/listener settings, and Server
identity. Review the installer prompts before proceeding; services may restart.
This restores the default and does not require Agent re-enrollment. Do not edit
`config.json` or invent a `set` command for this internal field.

Review retained terminal records before recovery: subsequent enrollment
lifecycle cleanup can remove terminal records older than 30 days. Active
enrollments are not eligible for retention cleanup. If restoring a known healthy
configuration is more appropriate, use `system backup validate <FILE>` followed
by the documented same-version `system restore <FILE>` workflow; review its
broader state replacement and confirmation before proceeding. A new backup of
the invalid configuration preserves evidence but is not a healthy repair.

After recovery, run `show enrollments` and `system diagnostics` and verify that
the invalid-retention warning has cleared.

## 5. Connect a Managed Host

On the DRLink Server:

```text
set enrollment zero-touch
```

The guided workflow issues a one-time enrollment/install credential.

Ticket limits:

```text
maximum per request           10
maximum active unused         10
default TTL                   1 hour
maximum TTL                   24 hours
use count                     1
```

Raw ticket/install URL material is shown only at issuance. Server persistent state retains verifier/hash plus lifecycle metadata, not a redisplayable raw ticket.

For manual enrollment, an Enrollment Code is also a one-time authorization for a fresh enrollment operation. After enrollment succeeds, do not reuse that Code for uninstall/reinstall or a later recovery; create a new Enrollment Code instead. If the original `/enroll` response is lost or the installer is interrupted, the Agent resumes from its protected local pending-enrollment state and replays only the original enrollment operation. This crash-recovery replay does not make the consumed Code valid for a new install.

## 6. Agent verification

After successful enrollment, on the Agent Host verify:

```text
show status
show agent
system info
system diagnostics
```

The role must be shown as `Agent Host`.

## 7. Create connectivity

Remote Service creation occurs on the owning Agent Host.

Example:

```text
set remote-service ssh-access
```

or complete one-shot form:

```text
set remote-service ssh-access destination this-host service ssh enabled
```

Remote Access policy is configured on the Server and is independent from Remote Service creation.

## 8. External infrastructure boundary

Data Relay Link does not silently create or modify:

- cloud security groups;
- customer firewall/NAT/DNAT rules;
- DNS-provider records;
- OS users/passwords;
- SSH server configuration;
- application TLS certificates.

Those prerequisites remain operator/environment responsibility unless an explicitly approved future product feature says otherwise.

## 9. Installation validation

A production candidate is not considered installed/qualified merely because bootstrap exits successfully.

At minimum verify:

```text
product identity
role
service health
management identity
Zero-Touch/enrollment
Remote Service lifecycle
policy behavior
reboot persistence
uninstall/reinstall where required by the release gate
```

Use `RELEASE_VALIDATION.md` and the exact release checklist for candidate qualification.
