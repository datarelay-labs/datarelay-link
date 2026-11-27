<h1 align="center">Data Relay Link</h1>

<p align="center">
  <strong>격리·제한 네트워크를 위한 Secure Connectivity.</strong>
</p>

<p align="center">
  네트워크 전체를 연결하지 않고 실제로 필요한 연결만 Relay합니다.
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>한국어</strong> · <a href="https://link.datarelay.run/">제품 웹사이트</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/development-v2.4.0-F59E0B?style=flat-square" alt="Development target v2.4.0">
  <img src="https://img.shields.io/badge/channel-development-64748B?style=flat-square" alt="Release channel development">
  <img src="https://img.shields.io/badge/FRP-v0.71.0-2563EB?style=flat-square" alt="FRP v0.71.0">
  <img src="https://img.shields.io/badge/license-Source%20Available-111827?style=flat-square" alt="Source Available">
  <img src="https://img.shields.io/badge/management-CLI--first-7C3AED?style=flat-square" alt="CLI-first">
</p>

<p align="center">
  <strong>제품 웹사이트:</strong> <a href="https://link.datarelay.run/">link.datarelay.run</a>
</p>

---

> **라이선스 — Source Available:** Data Relay Link는 개인 사용 및 조직 내부 상업 운영에 무료입니다. 내부 소스 수정은 허용됩니다. 재판매, 상업적 재배포, OEM/화이트라벨, 경쟁·파생 상업 제품, SaaS/호스팅/관리형 서비스 제공에는 별도의 서면 commercial license가 필요합니다. 자세한 내용은 [LICENSE](LICENSE)와 [LICENSING.md](LICENSING.md)를 참고하십시오.

## Data Relay Link란

Data Relay Link는 공식 pinned [`fatedier/frp`](https://github.com/fatedier/frp)를 기반으로 한 lightweight, CLI-first secure connectivity layer입니다.

NAT, Firewall, 제한 네트워크 뒤의 시스템이 사용자가 관리하는 Server로 outbound 연결을 만들고, 의도적으로 승인한 서비스와 접근 경로만 Relay합니다.

핵심 원칙:

> **네트워크 전체를 연결하지 마십시오. 실제로 필요한 연결만 Relay하십시오.**

Full VPN, network overlay, RMM platform, custom FRP fork를 구축하는 복잡성을 피하는 것이 목적입니다.

## 세 가지 연결 / 접근 plane

```text
Remote Access     outside → approved internal Remote Service
Internet Access   managed/protected source → approved outside destination
AI Access         authenticated AI Identity → approved target permissions
```

## 현재 v2.4 public model

```text
Managed Host / DRLink Agent

Network Object / Network Group
Service Object / Service Group
Permission Object / Permission Group

AI Identity
Remote Service

Remote Access
Internet Access
AI Access

Remote Access: BLACKLIST / WHITELIST
Internet Access: WHITELIST only, deny-by-default
AI Access: WHITELIST only, deny-by-default

ConfigurationBundle
```

초기 정책 상태는 plane마다 다릅니다. Remote Access는 No Policy / No Rules에서 실효 접근이 ALLOW이고,
Internet Access와 AI Access는 No Policy / No Rules에서 DENY ALL입니다.
Remote Access는 BLACKLIST 또는 WHITELIST를 지원하고, Internet Access와 AI Access는 WHITELIST만 지원합니다.
BLACKLIST는 일치하는 enabled Rule을 deny하고, WHITELIST는 일치하는 enabled Rule을 allow합니다.
Rule은 순서가 없으며 Rule별 ALLOW/DENY action을 갖지 않습니다.
Policy Rule은 접근을 허용하거나 거부할 뿐, connectivity 자체를 만들지 않습니다.

## Architecture 요약

```mermaid
flowchart LR
    O["Operator / Approved Client"] --> P["Data Relay Link Server<br/>Public Endpoint"]

    A["Managed Host A<br/>NAT / Firewall"] -->|Outbound FRP tunnel| P
    B["Managed Host B<br/>NAT / Firewall"] -->|Outbound FRP tunnel| P
    C["Managed Host C<br/>NAT / Firewall"] -->|Outbound FRP tunnel| P

    P --> S1["Remote Service SSH"]
    P --> S2["Remote Service HTTP / HTTPS"]
    P --> S3["Remote Service Custom / Fixed TCP"]
```

```text
                    Data Relay Link
                          │
           Embedded SQLite control plane
                  /var/lib/drlink/drlink.db
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   Remote Access    Internet Access      AI Access
   inbound relay    controlled egress    MCP Bridge
```

외부 database 서비스는 필요하지 않습니다. Server는 Linux 기반입니다. macOS와 Windows는 검증된 platform matrix에 따라 Agent Host로 지원됩니다.

Docker Server 배포는 v2.4 target에 포함되지 않으며 이후 release line roadmap 항목입니다.

## 주요 기능

| 기능 | 제공하는 것 |
|---|---|
| **Zero-Touch enrollment** | Short-lived enrollment credential로 빠른 Managed Host 온보딩 |
| **Stable identity** | Immutable Managed Host identity와 persistent Remote Service identity |
| **Stable endpoint** | 정상 lifecycle에서 public-port reservation 유지 |
| **Remote Services** | Agent 소유의 TCP / Fixed TCP connectivity (UDP Remote Service는 거부) |
| **LAN reachability** | 로컬 Managed Host 또는 도달 가능한 internal-LAN host에 publish |
| **Access Policy** | Remote Access는 BLACKLIST / WHITELIST, Internet / AI Access는 WHITELIST-only deny-by-default |
| **AI Access / MCP** | Verified AI Identity → Permission을 통한 MCP Bridge 접근 |
| **ConfigurationBundle** | Server/Agent 원자성 범위의 multi-resource 변경 세트 |
| **Health & operations** | Doctor, support bundle, lifecycle, backup/restore |
| **단일 운영 인터페이스** | 일반 운영은 `sudo drlink` |

## Server vs Agent Host CLI context

기본 운영 인터페이스:

```bash
sudo drlink
```

| Context | 소유 범위 |
|---|---|
| **Server** | Managed Hosts, Network/Service/Permission Object·Group, Access Policy, Internet Access, AI Access / AI Identity, Server ConfigurationBundle |
| **Agent Host** | 해당 Agent의 local lifecycle과 소유 Remote Service, Agent ConfigurationBundle |

Remote Service mutation은 소유 Agent Host에서만 수행됩니다. Server의 Remote Service 설정 조회는 read-only입니다. destination이 다른 host이면 현재 Agent Host가 Relay Host가 됩니다.

## 안전한 빠른 시작 / discovery

immutable `v2.4.0` 태그가 생기기 전에는 exact SHA 또는 owner가 지정한 candidate artifact로만 설치하십시오. `v2.4.0/dist/bootstrap-server.sh` 형태의 태그 URL은 태그가 생성되기 전까지 404입니다.

온라인 Server 설치는 아래 방식을 권장합니다. 승인된 exact SHA를 지정하면 작은 Bootstrap이 공통 파일과 플랫폼별 필수 아카이브를 진행률·타임아웃·SHA256 검증과 함께 다운로드합니다. 기존 `dist/bootstrap-server.sh`는 오프라인 설치용으로 유지합니다.

```bash
REF='<EXACT_SHA>'
curl -fL --connect-timeout 10 --max-time 30 "https://raw.githubusercontent.com/datarelay-labs/datarelay-link/$REF/dist/bootstrap-server-online.sh" | sudo bash -s -- "$REF"
```

설치 후 상태를 바꾸지 않는 discovery 명령을 우선 사용하십시오:

```bash
sudo drlink system version
sudo drlink show status
sudo drlink system diagnostics
```

Data Relay Link는 외부 firewall/NAT, cloud security group, DNS provider record, SSH account, application certificate를 자동으로 변경하지 않습니다.

## Zero-Touch enrollment

Server에서 현재 vocabulary로 enrollment를 발급합니다:

```text
set enrollment zero-touch
```

(또는 Guided menu → Managed Hosts → Connect a Managed Host)

고정 8자리 진입 목표는 Linux/macOS `curl -kfsS https://remote.xdr.ooo/A3xK9mP2|sudo bash` 및 Windows 관리자 PowerShell `iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9mP2|Out-String)`입니다. 공인·사설 HTTPS 동일 구문, 고객 장비 사전 설치 불필요. 명령 발급 시 최초 유효 Agent의 자동 등록이 승인됩니다. 명령은 비공개로 전달하며 후속 Bootstrap이 다운로드·검증·등록·재실행 처리를 수행합니다. 최초 `-k`는 서버 인증을 제공하지 않습니다. [표준 설계](docs/ZERO_TOUCH_REGRESSION_CONTROL.md)를 참조하십시오. 실제 제품 검증은 미완료입니다.

Managed Host가 enroll되고 Remote Service가 enabled되면 예약된 public endpoint로 연결합니다:

```text
ssh -p <public-port> <username>@<public-hostname>
```

SSH 연결 예시의 username은 hint metadata일 뿐입니다. 검증된 local account를 쓰거나 `<username>`을 표시하십시오. **기본 username은 없습니다.**

Zero-Touch는 다음을 하지 **않습니다**:

- 네트워크 전체 연결
- enrollment 인증 생략
- OS 사용자 생성, 비밀번호 설정, SSH Server 설치, `sshd_config` 변경

## Remote Service lifecycle

Remote Service는 Agent Host가 소유하는 실제 connectivity입니다:

```text
Agent Host
+ single destination
+ one Service Object
→ Remote Service
→ stable DRLink endpoint
```

Remote Service는 TCP와 Fixed TCP Service Object만 지원합니다. UDP Remote Service는 지원되지 않습니다.

실효 inbound access 조건:

```text
Enabled Remote Service
+
Reachable connector/target
+
Remote Access policy permits the flow
(or no policy is configured)
```

정상 lifecycle은 identity와 public-port reservation을 보존하도록 설계되어 있습니다. disable/enable, revoke, uninstall, release는 서로 다른 의미입니다. 정확한 matrix는 Product Master와 CLI/AI Master를 참고하십시오.

## Internet Access와 AI Access

### Internet Access

보호된 host는 표준 HTTP/HTTPS proxy 설정을 사용할 수 있습니다. gateway는 명시적으로 승인된 destination/protocol/port만 허용합니다.

보안에는 다음이 포함됩니다:

```text
WHITELIST-only deny-by-default policy enforcement
fail-closed unsafe-destination checks
server-side DNS
DNS rebinding resistance
SSRF/private/local/metadata protection
safe CONNECT/SNI behavior
explicit public Host/CIDR policy where supported
Fixed TCP through the same authority
```

기술 능력명: **Controlled Egress**. 일반 CLI/resource 이름: **Internet Access**.

현재 Rust 마이그레이션의 R1은 Python이 승인하고 연결한 뒤의 양방향 TCP relay로
범위를 제한합니다. MCP R2는 기존 Python dispatch 예산을 원자적으로 제한하는 Rust
helper를 추가합니다. CLI, OAuth/AI Identity, AI Access 정책, SQLite 및 durable job,
nonce, audit 권한은 Python에 유지됩니다. Rust relay가 없거나 재검증 callback이
실패하거나 정책이 철회되면 연결을 닫습니다. native library가 없는 자동 모드에서는
handoff 전에 Python relay를 사용하고, 명시적인 Rust 선택은 library 부재 시 fail-closed입니다.
handoff 이후 세션을 Python relay로 재실행하지 않으며, 새 연결은 `DRLINK_EGRESS_RUNTIME=python`으로 기존 Python rollback 경로를
선택할 수 있습니다. 각 방향의 relay queue는 256 KiB로 제한하며, peer hangup 뒤에도
수신 EOF까지 대기 데이터를 전달하고 backpressure 중 유휴 descriptor를 poll에서 제외합니다.
Rust MCP helper는 dispatch admission, 1 MiB 결과 보존 창/64 KiB cursor page, 64 KiB 제한
response body 쓰기를 제공합니다. 실제 socket/TLS 쓰기, HTTP framing, backpressure는 Python
handler가 담당합니다. 결과 대기와 inbound connection I/O 통합은 아직 남아 있습니다. R3 stdout/stderr drain은
Linux/macOS Agent 및 Server 경로에 연결됐습니다. Linux 회귀는 통과했고, Apple Silicon은
native capture 종료 처리 실패를 수정해 재검증 중입니다. 두 Rust library는 아직 설치 패키지에 포함되지 않았고 실제 사용자
E2E qualification도 진행 중입니다. MCP rollback은 `DRLINK_MCP_RUNTIME=python`이며,
`auto`는 library가 없으면 Python으로 돌아가고 명시적 `rust` 선택은 library 부재 시
서비스 초기화를 fail-closed 합니다.
R3에서는 Python이 시작한 Linux/macOS Agent 및 Server executor 자식 프로세스의
stdout/stderr pipe를 Rust가 poll하고 읽습니다. macOS는 kqueue process-exit event로
종료를 관찰하고, Linux는 waitid를 사용합니다. process 시작,
timeout 선택, process-group 종료, wait/reap 권한은 Python에 유지됩니다.
또한 MCP job 출력은 Rust가 기존 1 MiB 보존 창과 64 KiB cursor 페이지를 제공하고,
Python이 job 소유권과 cursor 검증, 응답 생성을 계속 담당합니다. 연결 I/O와 결과 대기는
R2에 남아 있으며, native shared library의 설치 패키징은 아직 완료되지 않았습니다.

### AI Access / MCP

MCP Bridge는 v2.4.0 **target**에 포함되며, stable release 전에 qualification이 필요합니다. 이미 출시된 stable 기능으로 설명하지 마십시오.

```text
AI Host / tool
   │
 MCP over HTTPS
   │
Data Relay Link Server MCP Bridge
   │
AI Access policy
   │
existing authenticated DRLink control path
   │
Managed Host / private target
```

AI Access의 Source는 검증된 **AI Identity**입니다. [AI MCP Setup 사용 가이드](docs/AI_ACCESS_MCP.md)는 Managed Host 등록, AI MCP Setup(인증), 방화벽 방식의 Access Rules(Source, Destination, Permission)를 분리합니다. AI MCP Setup에서 MCP 준비 상태를 확인하며, 기본 권한은 Object를 직접 만들지 않아도 선택할 수 있습니다. 사용자 정의 Object/Group은 고급 기능으로 유지하고 인증 자체는 접근 권한을 부여하지 않습니다. 후보 버전의 동작이며 설치된 릴리즈의 검증 상태는 별도로 확인합니다.

## ConfigurationBundle / AI-assisted configuration

독립적인 단일 resource에는 direct CLI를 사용하십시오.

서로 의존하는 여러 resource에는 ConfigurationBundle을 사용하십시오. Human Wizard, AI one-shot CLI, ConfigurationBundle은 하나의 Change Plan / mutation engine을 공유합니다.

원자성 범위는 현재 CLI context입니다:

```text
Server ConfigurationBundle  → Server에서 atomic
Agent ConfigurationBundle   → 해당 Agent Host에서 atomic
```

Server+multi-Agent를 아우르는 단일 분산 transaction은 없습니다. Bundle에서 생략은 변경 없음, `state: absent`는 명시적 삭제/reset입니다.

## Release / development 상태

```text
PROJECT_VERSION=2.4.0
RELEASE_CHANNEL=development
FRP_VERSION=0.71.0
```

현재 project version: **2.4.0**<br>
현재 pinned FRP version: **v0.71.0**

이 저장소 트리는 branch
[`feature/v2.4.0-final-product-closure`](https://github.com/datarelay-labs/datarelay-link/tree/feature/v2.4.0-final-product-closure)
위의 **v2.4.0 development target**입니다. exact-HEAD qualification이 끝나기 전에는 stable `v2.4.0` 태그가 없습니다. repository metadata가 실제로 해당 channel로 바뀌지 않는 한 이 branch를 stable, RC, preview로 취급하지 마십시오.

Version policy는 다음을 구분합니다:

```text
Documented stable baseline     v2.3.0
Older published release        v2.2.1
Not manufactured               v2.3.1
Current development target     2.4.0 / development channel
```

역사적 태그만으로 현재 stable 지위를 발명하지 마십시오.

태그 전 installer/bootstrap은 존재하지 않는 미래 stable 태그가 아니라 immutable exact SHA 또는 immutable candidate artifact를 사용해야 합니다. 태그 후 의도된 형태:

```text
.../datarelay-labs/datarelay-link/v2.4.0/dist/bootstrap-server.sh
```

이 경로는 immutable 태그가 생기기 전까지 404입니다.

Repository: [`datarelay-labs/datarelay-link`](https://github.com/datarelay-labs/datarelay-link)

가변 `main`은 정상 설치/업데이트 경로가 아닙니다. 개발 및 사전 릴리즈 검증은 exact immutable source SHA 또는 명시적으로 qualification 된 candidate artifact를 사용합니다.

구 updater의 legacy client는 one-time verified compatibility bridge가 필요할 수 있지만, 이 호환 경로가 현재 immutable-source update policy를 대체하지 않습니다.

Stable release는 동일 final exact HEAD에서 세 access plane과 해당 lifecycle/platform gate를 포함한 Real E2E 2회 통과가 필요합니다. code/dependency 변경 시 pass counter가 초기화됩니다.

## 문서

공개 문서: https://link.datarelay.run

시작 지점:

- [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) — 문서 권위/상태 인덱스
- [`docs/PRODUCT_MASTER.md`](docs/PRODUCT_MASTER.md) — 제품 수준 결정
- [`docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`](docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md) — CLI/AI SSOT
- [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) — target direct grammar
- [`docs/Data Relay Link CLI Information Architecture.md`](docs/Data%20Relay%20Link%20CLI%20Information%20Architecture.md) — CLI UX
- [`docs/CONFIGURATION_BUNDLE.md`](docs/CONFIGURATION_BUNDLE.md) — declarative / AI copy-paste contract
- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — Server/Agent 설치 및 enrollment
- [`docs/UPGRADE.md`](docs/UPGRADE.md) — 업그레이드 채널, migration, rollback
- [`docs/REMOTE_ACCESS.md`](docs/REMOTE_ACCESS.md) — Remote Service와 Remote Access 운영
- [`docs/AI_ACCESS_MCP.md`](docs/AI_ACCESS_MCP.md) — AI Identity, permission, AI Access, MCP
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — 진단 및 복구 가이드
- [`docs/CONTROLLED_EGRESS.md`](docs/CONTROLLED_EGRESS.md) — Internet Access 동작
- [`docs/SECURITY.md`](docs/SECURITY.md) — 보안 경계
- [`docs/VERSION_POLICY.md`](docs/VERSION_POLICY.md) — version/release 규칙
- [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) — final stable gate
- [`docs/CONTROL_PLANE_ARCHITECTURE.md`](docs/CONTROL_PLANE_ARCHITECTURE.md) — 내부 architecture/history

## Non-goals

v2.4.0은 다음을 요구하지 않습니다:

```text
Web UI
Docker Server deployment
external database server
central SaaS control plane
HA database cluster
hundreds/thousands-host orchestration
VPN / full network overlay
SASE / SWG / CASB / DLP
TLS inspection
automatic firewall / DNS management
```

## Source Available license

**Data Relay Link는 source available이며 open source가 아닙니다.**

통제 조건과 쉬운 요약은 [LICENSE](LICENSE)와 [LICENSING.md](LICENSING.md)를 참고하십시오.
