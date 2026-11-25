# Zero-Touch Bootstrap — fixed short entry design

**ZT-P0-CONTRACT-20261026 — fixed eight-character entry target (owner revision 2026-11-25).** The customer starts with one OS-native command, one HTTPS authority (FQDN or IP), and one eight-character root-path file locator. Public and private HTTPS use the same target form. No preinstalled DataRelay software, inline configuration, separate enrollment ID, fingerprint, artifact hash, or installer body in the customer command. All subsequent configuration, downloads, verification, installation, recovery and enrollment belong to the multi-stage Bootstrap; their size and count are unrestricted. Issuing the command authorizes one automatic registration by the first valid signed Agent claim. Treat the short locator as a sensitive, expiring bearer capability; it is not the downstream enrollment code. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for exact target templates, the automatic first-claim policy, the explicit initial-transport risk and actual acceptance status. This is a design target, not installed-product qualification.

## Command fields

Only the Server authority (FQDN or IP, optional configured port) and eight-character root-path Bootstrap filename vary. The downloader, HTTPS protocol, download options and execution wrapper are fixed per OS by the [canonical field table](ZERO_TOUCH_REGRESSION_CONTROL.md#command-fields-normative). No other customer command information is allowed.

## Operator workflow

Select OS and enrollment profile on the Server. Copy the generated one-line entry command and send it to the customer through the established communication channel.

- Linux/macOS: `curl -kfsS https://remote.xdr.ooo/A3xK9mP2|sudo bash`
- Windows (administrator PowerShell): `iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9mP2|Out-String)`

No client-side preinstallation, CA registration, secondary command, or user-facing configuration fields. These are target templates pending product qualification; Windows native execution is unverified.

The Server grants registration authority when the operator issues the command. Share the command privately. The Agent creates its key and automatically registers; no second customer command, fingerprint exchange or Server-side approval is needed.

The first valid signed claim atomically binds one machine and key. The Agent proves possession again when redeeming the internal credential and signing enrollment. A different machine or key is rejected; the same Agent can retry safely before expiry and resume a committed enrollment. Existing six-character tickets are no longer accepted by the entry endpoint. Revoke and reissue outstanding tickets; existing enrolled Agents are unaffected.

## Server entry endpoint

Serve `GET /<eight-character-locator>` on the configured HTTPS authority. Allocate collision-checked, expiring, rate-limited locators; treat the locator as a sensitive first-claim capability, not as the internal enrollment code. Select the platform-specific bootstrap at issuance. Route only the exact eight-character path pattern to the entry handler; reserve existing product routes, do not proxy every path. Use consistent redaction and avoid response caching.

## Bootstrap processing

Stage 1 retrieves and processes any necessary files or commands. Stage 2 performs artifact verification and downstream authenticated connections. Stage 3 performs automatic first-claim enrollment, atomic single-use redemption and service configuration. Keep credentials out of the entry file, preserve existing identity and port reservations on retry, and print an explicit install result. No arbitrary restriction on later-stage size or download count.

## Configuration and readiness

`bootstrap_hostname` selects the entry authority; `public_hostname` remains the Remote Service access alias. FQDN and numeric-IP deployment are supported targets. Setting the hostname does not create DNS, firewall/NAT or certificates. Public and private certificate entry use the same template. Readiness must verify reachability and the actual locator handler; downstream authenticated enrollment and installer readiness remain separate.

## Trust and release scope

The initial `-k` is a deliberately unauthenticated TLS fetch in the requested target, not server authentication. Do not propagate it to management-plane TLS. The operator communication channel authenticates the command, not the network response. An eight-character locator cannot independently authenticate the intended Agent. The owner explicitly accepts initial -k and automatic first-claim registration for this design. Anyone who obtains the locator may attempt to claim it first. The signed Agent key and separate one-time enrollment credential bind the winning identity; they do not remove that initial bearer risk. Native installed-product qualification and release acceptance still require actual evidence. See [canonical contract](ZERO_TOUCH_REGRESSION_CONTROL.md).
