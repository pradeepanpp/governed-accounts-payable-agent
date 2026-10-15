# Container security: residual risk register and deployment decision

**Project:** Governed Autonomous Accounts Payable AI Agent (research prototype)  
**Review baseline:** Trivy 0.70.0, October 14, 2026  
**Image:** Python 3.11 on Debian 13 Trixie, Tesseract English and Arabic, non-root UID 10001

## Scan evidence and interpretation

| Measure | Debian 12 Bookworm | Debian 13 Trixie candidate |
|---|---:|---:|
| CRITICAL package findings | 4 | 1 |
| HIGH package findings | 94 | 75 |
| Total HIGH/CRITICAL findings | 98 | 76 |
| Python-library findings | 2 | 0 |
| Findings with a fixed version *listed by Trivy* | 2 | 0 |

These are package/vulnerability findings, **not** demonstrated remote exploits or necessarily distinct CVEs. All 76 candidate findings concern OS packages. A blank `FixedVersion` does not prove there is no patch on another distribution or in a future database update. Re-run the scan before every deployment decision; image tags and vulnerability databases change over time.

## Priority risk register

| ID / package | Reported severity and exposure condition | Current position and decision |
|---|---|---|
| `CVE-2026-6653` / `libxml2` | **CRITICAL**; memory-safety defect when an affected XML parser processes crafted content. The HTTP API accepts PDFs, not arbitrary XML, but transitive parsing reachability has **not been established**. | **Open / escalation required.** Trivy candidate report lists no Trixie fixed version. Track Debian advisory; examine library call paths. Block public deployment until reachability is assessed and residual risk is explicitly accepted or remediated. |
| `libxml2` HIGH findings (seven in candidate report) | Crafted XML and affected parser operations; package presence alone does not prove reachable processing. | **Open.** Review CVE-specific conditions and transitive consumers; do not silence through blanket ignore rules. |
| `libtesseract5` + `tesseract-ocr` (12 package findings, six CVE IDs) | Several reported exploits require attacker-supplied `.traineddata` or malicious model files. Users upload PDFs, **not** OCR model files; trusted OS language data is used. Other affected paths need case-by-case review. | **Open / restricted input.** Do not allow uploaded/custom OCR models. Keep language data immutable in deployment. Track Debian fixes. Validate OCR sandboxing and limits. |
| `libexpat1` (five HIGH findings) | Potential memory-safety/denial-of-service conditions in XML parsing, depending on callbacks/input and transitive library usage. | **Open.** Determine if PDF/native-render path can invoke Expat; if yes, prioritize patches/isolated process execution. |
| `libtiff6` (two HIGH findings) | Image-decoding vulnerabilities may be more relevant to untrusted scanned PDFs if TIFF functionality is reachable through rendering libraries. | **Open / higher relevance.** Investigate actual decoder use and restrict untrusted document processing. Track distribution fixes. |
| Other OS findings | Utility, core-library and system-package flaws often require specific capabilities not exposed by the API. | **Open / review.** Do not conclude "not exploitable" from package names alone; review on each scan. |

### Existing, verified and proposed controls

- **Implemented/tested:** non-root container account; authenticated API key; bound PDF size/page counts; OCR subprocess timeout and cumulative budget; review-only `ESCALATE` action; no actual payment execution; real scanned-PDF OCR in Docker CI.
- **Not yet validated for public deployment:** container read-only root filesystem, dropped Linux capabilities, memory/CPU/PID limits, outbound-network restrictions, seccomp/AppArmor policy, request-rate enforcement under load, process-level resource bounds for all native PDF/rendering operations, and a production secrets lifecycle.
- **CI policy:** preserve the full JSON report; **fail** on HIGH/CRITICAL findings for which Trivy supplies a non-empty `FixedVersion`; **do not suppress** unfixed findings. A passing fixable-only gate is **not** a security clearance.

## Deployment decision — NOT APPROVED for public internet exposure

**Decision status: HOLD.** This project remains a research and local demonstration system; do not publish a public invoice-upload endpoint, connect real ERP/payment accounts, or process real customer invoices at this stage.

**Prerequisites to reconsider:**

1. CI passes Python regression tests, real authenticated PDF/OCR integration, and the fixable vulnerability gate; full security JSON artifact is retained.
2. Review `CVE-2026-6653` and document concrete XML parser reachability, relevant package fixes, or formally accepted residual risk with named approver/date and review expiry.
3. Investigate applicable `libtiff`, `libexpat`, and Tesseract CVEs based on actual processing paths; patch or isolate affected operations wherever possible.
4. Demonstrate hardened runtime configuration: non-root, read-only root filesystem when feasible, dropped capabilities, memory/CPU/PID restrictions, and limited egress; verify failures safely escalate without payment execution.
5. Obtain an explicit new deployment authorization after risk review. **A CI green check is not authorization.**

**Decision owner:** Project maintainer. **Recorded:** October 15, 2026. **Re-review:** Before any externally reachable deployment and following any material image/dependency change.

**Evidence:** `trivy-image-report.zip` (Bookworm), `trivy-image-report (1).zip` (Trixie), downloaded GitHub Actions artifacts; source vulnerability records are advisory data, not proof of exploitability.
