# Zero-Touch Bootstrap — fixed short entry design

**ZT-P0-CONTRACT-20261026 — fixed six-character entry target (owner revision 2026-11-24).** The customer starts with one OS-native command, one HTTPS authority (FQDN or IP), and one six-character root-path file locator. Public and private HTTPS use the same target form. No preinstalled DataRelay software, inline configuration, separate enrollment ID, fingerprint, artifact hash, or installer body in the customer command. All subsequent configuration, downloads, verification, installation, recovery and enrollment belong to the multi-stage Bootstrap; their size and count are unrestricted. The locator is not an enrollment credential. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for exact target templates, the independent enrollment requirement, the explicit initial-transport risk and actual acceptance status. This is a design target, not installed-product qualification.

## Operator workflow

Select OS and enrollment profile on the Server. Copy the generated one-line entry command and send it to the customer through the established communication channel.

- Linux/macOS: `curl -kfsS https://remote.xdr.ooo/A3xK9m|sudo bash`
- Windows (administrator PowerShell): `iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9m|Out-String)`

No client-side preinstallation, CA registration, secondary command, or user-facing configuration fields. These are target templates pending product qualification; Windows native execution is unverified.

## Server entry endpoint

Serve `GET /<six-character-locator>` on the configured HTTPS authority. Allocate collision-checked, expiring, rate-limited locators; never treat a locator as a bearer enrollment credential. Select the platform-specific bootstrap at issuance. Route only the exact six-character path pattern to the entry handler; reserve existing product routes, do not proxy every path. Use consistent redaction and avoid response caching.

## Bootstrap processing

Stage 1 retrieves and processes any necessary files or commands. Stage 2 performs artifact verification and downstream authenticated connections. Stage 3 performs independently authorized enrollment, atomic single-use redemption and service configuration. Keep credentials out of the entry file, preserve existing identity and port reservations on retry, and print an explicit install result. No arbitrary restriction on later-stage size or download count.

## Configuration and readiness

`bootstrap_hostname` selects the entry authority; `public_hostname` remains the Remote Service access alias. FQDN and numeric-IP deployment are supported targets. Setting the hostname does not create DNS, firewall/NAT or certificates. Public and private certificate entry use the same template. Readiness must verify reachability and the actual locator handler; downstream authenticated enrollment and installer readiness remain separate.

## Trust and release scope

The initial `-k` is a deliberately unauthenticated TLS fetch in the requested target, not server authentication. Do not propagate it to management-plane TLS. The operator communication channel authenticates the command, not the network response. A six-character locator cannot authenticate an agent. Independent enrollment authorization and the initial-execution security disposition remain open; no installed-product qualification until actual evidence. See [canonical contract](ZERO_TOUCH_REGRESSION_CONTROL.md).
