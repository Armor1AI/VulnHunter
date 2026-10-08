# VulnHunter for OpenCode (`vulnhunt`)

The core VulnHunter scanner skill for [OpenCode](https://opencode.ai/).
It maps every user-controllable input in a codebase, traces each one *forward*
to dangerous sinks, runs an adversarial pipeline to disprove weak candidates,
and emits only findings it can back with a static proof, exploit-test source,
and a proposed fix. This is a **prompt-only** skill — `SKILL.md` plus the phase files
under `phases/`; there is no Python package to install.

## Install

From the repository root, install the scanner, OpenCode command, and restricted
agents into `~/.config/opencode/`:

```bash
./install-opencode.sh
./uninstall-opencode.sh
```

On Windows:

```bat
install-opencode.cmd
uninstall-opencode.cmd
```

The installer copies files rather than symlinking them. Re-run it after pulling
or editing the scanner.

## Usage

```bash
OPENCODE_CONFIG="$HOME/.config/opencode/vulnhunt.static.json" \
  opencode run --agent vulnhunt-orchestrator \
  "Load the vulnhunt skill and follow it exactly. Scan the current repository. Perform a static, no-Bash audit."
```

The scan writes its artifacts to a `*_VULNHUNT_RESULTS_*` directory (report
`README.md`, static PoCs, and exploit-test source). VulnHunter **never modifies
the target codebase** — fix strategies are documented, not applied.

Automated callers may pre-create the results directory and pass its path,
repository URL, and branch in a `Pre-resolved scan metadata` block. The existing
`vulnhunter-agent/` and `harness/` remain Claude-specific and are not used by
the OpenCode scanner.

## Design: dispatcher + phase subagents

`SKILL.md` is an **orchestrator** — it never performs security analysis itself.
It creates the results directory, dispatches a subagent per phase, verifies each
subagent's output files exist, and compiles the final report. Keeping findings
out of the orchestrator's context is deliberate: it forces the systematic
methodology instead of improvised analysis.

| Phase | File | Responsibility |
|-------|------|----------------|
| 1 · Recon | `phases/phase1_recon.md` | Build the input inventory, partition the codebase, annotate production reachability. |
| 2 · Hunt | `phases/phase2_hunt.md` + `phase2_class_{inj,nav,log}.md` | Parallel class agents (injection / navigation-&-access / logic-&-crypto) trace inputs to sinks per partition, plus one sink-driven audit agent. |
| 2b · Verify | `phases/phase2b_verify.md` | Adversarial pass that tries to *disprove* each candidate; ~half are eliminated. |
| 3 · Reproduce | `phases/phase3_reproduce_test.md` + `phase3c_fixes.md` | Write PoCs, executable exploit tests, and fix strategies. |
| 3d · Sweep | `phases/phase3d_sweep.md` | Grep every confirmed root-cause pattern across the whole codebase. |
| 4 · Report | `phases/phase4_report.md` | Orchestrator compiles the final report. |

`phase2_shared.md` holds the reference material every class agent reads first, so
it is cached across the parallel dispatch.

## Requirements

- OpenCode 1.18.31 or later with a configured model.
- Python is not required. The provided agents deny `bash`, network tools, and
  edits outside `*_VULNHUNT_RESULTS_*` directories.

## License

Part of the VulnHunter project; licensed under the Apache License, Version 2.0.
See the repository-root [`LICENSE`](../LICENSE).
