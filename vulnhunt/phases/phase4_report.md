# Final Report Format

> **Context**: All phases are complete. Compile the final report with all confirmed
> findings, code smells, and the resolved input inventory.

## Final Report Format

**IMPORTANT**: All findings describe the original source code as it existed at
scan time. The audit does not modify source files.

**Each confirmed instance is a separate finding.** If the sweep produced 5 candidates
for the same root cause and 3 are STATIC-CONFIRMED by the full pipeline, the report contains 3
VULN-NNN entries — one per sink location, each with its own data flow, PoC, and
exploit test. They may share a root cause description and fix strategy, but each
gets its own ID and its own row in the summary table.

Start the report with a summary table of all confirmed findings.
**This table MUST have one row per STATIC-CONFIRMED finding — not one row per root cause.**
If you have 2 root causes but 8 confirmed sink locations, the table has 8 rows.

Before writing it, reconcile the machine-readable ledgers. The report and
`findings.manifest` must contain exactly every Phase 3 `SURVIVING_ID` plus every
Phase 3d `ADDED_ID`. Do not report Phase 3 `INVALIDATED_ID` or `DOWNGRADED_ID`
entries as vulnerabilities. Every Phase 2b `CONFIRMED_ID` must already be
accounted for exactly once by Phase 3 as surviving, invalidated, or downgraded.

**Severity is immutable at this stage.** For Phase 3 survivors, copy each
finding's exact severity from the Phase 3 assignment table. For Phase 3d
additions, copy it from the authoritative `ADDED_SEVERITY` table in
`phase3d_output.md`. Do not reclassify or normalize any severity; in particular,
`High+` must remain `High+`, and `Low` or `Informational` Phase 3d additions must
remain present with that exact severity in the summary count, summary row, and
finding detail. The header must contain exactly one `Findings Summary` line,
computed directly from the two authoritative tables. Do not emit a draft,
alternative count, qualifier, or correction before or after it.

**Universal Auth Gap exception**: if Phase 2b §9 emitted
`VULN-PLATFORM-AUTHN` or `VULN-PLATFORM-AUTHZ`, that row leads the
summary table. Its body lists every `SUBSUMED-BY: VULN-PLATFORM-*`
finding (ID, file:line, CWE that would have been raised) so post-fix
re-scan can confirm the expected-to-disappear set. Subsumed entries do
NOT get their own summary-table rows. Put each subsumed numeric ID and its exact
`SUBSUMED-BY: VULN-PLATFORM-AUTHN` or `SUBSUMED-BY: VULN-PLATFORM-AUTHZ`
marker on the same line.

### Summary

| ID | Title | CWE | Severity | Evidence | Status |
|---|---|---|---|---|---|
| VULN-001 | [title] | CWE-XXX | High+/High/Medium/Low/Informational | [PoC](poc/VULN-001_description.md) \| [Test](exploit_tests/test_vuln_001_description.py) — NOT RUN (static evidence) | Confirmed |
| ... | ... | ... | ... | ... | ... |

Then for each finding, provide the full detail:

### [VULN-NNN] Title
| Field | Value |
|---|---|
| **Title** | ... |
| **Input** | inventory # and description |
| **CWE** | CWE-XXX: [Name] |
| **Severity** | High+/High/Medium/Low/Informational |
| **Location** | file:line (primary instance) |
| **Entry Point** | ... |
| **Data Flow** | source -> ... -> sink |
| **PoC** | [PoC](poc/VULN-NNN_description.md) |
| **Exploit Test** | [Test](exploit_tests/test_vuln_NNN_description.py) — NOT RUN; include STATIC-CONFIRMED rationale |
| **Fix** | [inline diff or link] |
| **Root Cause** | [shared root cause name, if this instance is part of a sweep group] |
| **Status** | Confirmed / Fixed / Verified |

When severity is **Informational** or **Medium** under the Authorization
Delegation Rule (phase2b_verify.md §8), include one extra row:
| **Trust Model** | one-line note recorded in Phase 2b |

Every finding MUST include a CWE identifier. Use the most specific CWE that applies
(e.g., CWE-89 for SQL injection, not CWE-74 for generic injection).

**VALIDATION RULE**: A finding is INVALID if either the **PoC** or **Exploit Test**
field is empty, says "N/A", or says "see above." Each field MUST contain a file path
to the saved artifact. If you cannot produce a PoC or exploit test, the finding has
not been proven and must be downgraded to Potential or eliminated.

**Code smells go in a separate section.** Findings where the exploit test showed
"code runs but attack is mitigated" are NOT vulnerabilities. List them after the
vulnerability findings under a "Code Quality / Defense in Depth" heading.

**Each code smell MUST include a downgrade rationale** explaining:
1. Which gate it failed or which exploit test defense blocked it
2. The specific evidence (file:line of the mitigation and the static test trace
   showing where the attack is blocked)
3. What condition would need to change for this to become exploitable (e.g.,
   "if the allowlist is removed," "if this route is exposed in production,"
   "if the downstream service stops validating")

Format:
| Field | Value |
|---|---|
| **Location** | file:line |
| **Pattern** | what the code does |
| **Downgrade reason** | which gate failed + evidence (file:line of mitigation) |
| **Risk if conditions change** | what would make this exploitable |
| **Recommendation** | why it should still be fixed |

They do not get VULN-NNN IDs or PoC files.

**Code smell generation (MANDATORY):** Before writing the Code Quality section,
systematically review these sources — not just findings that failed exploit tests:

| Source | What to look for |
|---|---|
| Gate 2b near-misses | Sanitizer correct for current sink but fragile (caller-dependent, wrong layer) |
| Gate 1 near-misses | Code exploitable if route were ever exposed; dev-only guard is the only protection |
| Security config | Missing SameSite, permissive trust proxy, missing security headers |
| Crypto inventory | Weak algorithm/mode where exploitation prerequisite is not currently met |
| Defense-in-depth gaps | Service-layer functions relying on caller sanitization with no own validation |

Each entry: location, risk, what prevents current exploitation, why it should be fixed.

**Include the sweep verification table.** After the code smells section, include
the final Phase 3d sweep table showing each root cause, the grep pattern used,
instances found/fixed/remaining. This demonstrates completeness — every root cause
was hunted across the entire codebase, not just at the initially-discovered location.

Save all artifacts to the `${VULNHUNT_DIR}/` directory:
```
${VULNHUNT_DIR}/
  README.md                         # Summary report with links (generated last)
  poc/
    VULN-001_sql_injection.md       # Static or runnable PoC
    VULN-002_path_traversal.md
  exploit_tests/
    test_vuln_001_sql_injection.py  # Executable exploit test
    test_vuln_002_path_traversal.sh
```

### Generating the README

After all findings are finalized, create `${VULNHUNT_DIR}/README.md` as the entry point.

**File creation is mandatory.** Use OpenCode's file-writing tool to create
`${VULNHUNT_DIR}/README.md`; do not print the report body as the chat response.
Then read the beginning of that path and verify the required header. Retry the
write if verification fails. The scan is incomplete until verification succeeds.

**The README MUST begin with this exact header structure** (fill in values):

```markdown
# VulnHunter Security Audit Report

**Run ID**: <VULNHUNT_DIR basename>
**Repository**: <full repo URL>
**Audit Date**: <YYYY-MM-DD>
**Branch**: <branch [short-commit-hash]>
**Model**: <model identifier>
**Findings Summary**: <N High+, N High, N Medium, N Low, N Informational>
```

Field definitions:
- **Run ID** = basename of `VULNHUNT_DIR` (the results folder name, e.g.
  `smartops-cli_VULNHUNT_RESULTS_2026-05-14-072642`).
- **Repository** = the `Repository URL` value supplied in the /vulnhunt
  kickoff prompt's pre-resolved metadata block. The agent layer already
  normalized SSH origins to https and stripped any `.git` suffix; use the
  value literally without running git or doing further parsing.
- **Branch** = the `VULNHUNT_BRANCH` value supplied in the same metadata
  block. Format: `branch-name [abc1234]`, or `unknown` if the source
  isn't a git repo. Do not run git to recompute.
- **Model** = the OpenCode `provider/model` identifier supplied by the caller,
  or `unknown` when the Boundary model broker intentionally hides it.

After the header, include:
- Summary table of findings (ID, title, severity, CWE, status)
- For each finding: input #, location, entry point, impact, links to PoC and exploit test files
- The resolved input inventory table showing every input's disposition
  (CANDIDATE / SAFE / DESIGN-INTENT) as a completeness artifact
- "Not Found / Excluded" section listing checked-but-clean vulnerability classes
- Artifacts table linking all files in `${VULNHUNT_DIR}/`

**Clickable links**: Every finding row in the summary table and every finding section
MUST include relative markdown links to the corresponding PoC file (`poc/VULN-NNN_*.md`)
and exploit test file (`exploit_tests/test_vuln_NNN_*`). Use the format
`[PoC](poc/VULN-001_desc.md) \| [Test](exploit_tests/test_vuln_001_desc.py)`.
A finding without clickable links to both artifacts is incomplete.

Before composing the README, read the `poc/` and `exploit_tests/` directory
listings and copy artifact filenames exactly; never derive or shorten them. In
Markdown tables, escape the separator between the PoC and test links as `\|` so
both links remain in the single Evidence cell.

**Cross-check**: The README summary table MUST list every VULN-NNN from the report.
Count the findings in the report and count the rows in the README table — they must
match. If they don't, you missed findings when generating the README.

After writing the README, add a footer to each PoC file linking to its exploit test
and back to the README.

Finally, read every local artifact path linked by the README. If any read fails,
correct the link and repeat the check. Do not report completion with unresolved
links or a summary row whose number of cells differs from its header.
Identify exposed credentials by location and type, but redact their values from
the README and all supporting artifacts.

### Finding manifest

After the README is final, write `${VULNHUNT_DIR}/findings.manifest`. Its first
line must be `FINDING_COUNT: N`, followed by one line per final report finding:

```text
FINDING_COUNT: 1
VULN-001|poc/VULN-001_sql_injection.md|exploit_tests/test_vuln_001_sql_injection.py
```

Use `FINDING_COUNT: 0` with no additional lines for a clean report. Each entry
must use the exact relative paths linked by the README. Do not include code
smells, eliminated candidates, or subsumed findings as separate entries.

**This is a strict plain-text machine-readable file, not Markdown.**
Its first byte must be the `F` in `FINDING_COUNT`; do not add a title, explanation,
blank line, BOM, list marker, or code fence before it. After writing the file,
read it back and verify that its first line is exactly `FINDING_COUNT: N`, that `N`
equals the number of following entry lines, and that those entries contain
exactly the reconciled Phase 3 survivors plus Phase 3d additions. If any check
fails, rewrite the complete file and verify it again before reporting completion.

Each final finding must reference its own exploit-test file; do not reuse a
test file across manifest entries. Its basename must also bind it to the finding
ID: `VULN-001` uses `test_vuln_001_*`, `VULN-PLATFORM-AUTHN` uses
`test_vuln_platform_authn_*`, and `VULN-PLATFORM-AUTHZ` uses
`test_vuln_platform_authz_*`. Do not swap otherwise distinct test files between
manifest entries.

## What NOT to Report

- Anything in test code, build scripts, vendored/third-party code, or generated code
  (see Operating Principle #5)
- Informational findings that aren't exploitable (exception: findings downgraded
  to Informational under the Authorization Delegation Rule ARE reported with
  full data flow and PoC — see phase2b_verify.md §8)
- Inputs with SAFE or DESIGN-INTENT dispositions in the inventory — these are not
  findings, but their dispositions ARE part of the audit record and should appear in
  the resolved inventory table in the report
- Dependencies with known CVEs — **do not perform deep analysis of dependency
  internals.** Instead: if you encounter a dependency CVE during hunting and the
  first-party code clearly invokes the vulnerable API path with attacker-controlled
  input (provable from the first-party call site alone), report it as a finding
  with the CVE reference. If exploitability would require analyzing the dependency's
  internal code to confirm, note it as a Code Smell with the CVE number and move on.
- Style issues or best-practice violations without security impact
- Theoretical vulnerabilities that require unrealistic preconditions
- Injection claims where the language/framework genuinely auto-sanitizes — but verify
  by reading the actual library, and check that the sanitizer matches the sink context
