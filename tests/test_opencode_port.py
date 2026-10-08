import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CORE_FILES = [
    REPO / "vulnhunt" / "SKILL.md",
    *(REPO / "vulnhunt" / "phases").glob("*.md"),
]


class OpenCodePortTests(unittest.TestCase):
    def test_installer_and_uninstaller_manage_the_opencode_scanner(self):
        with tempfile.TemporaryDirectory() as config_home:
            env = os.environ.copy()
            env["HOME"] = config_home
            env["XDG_CONFIG_HOME"] = str(Path(config_home) / "ignored-xdg")
            subprocess.run(
                [str(REPO / "install-opencode.sh")],
                cwd=REPO,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            installed = Path(config_home) / ".config" / "opencode"
            expected = {
                "skills/vulnhunt/SKILL.md": REPO / "vulnhunt/SKILL.md",
                "commands/vulnhunt.md": REPO / "opencode/commands/vulnhunt.md",
                "agents/vulnhunt-orchestrator.md": REPO
                / "opencode/agents/vulnhunt-orchestrator.md",
                "agents/vulnhunt-worker.md": REPO
                / "opencode/agents/vulnhunt-worker.md",
                "vulnhunt.static.json": REPO
                / "opencode/opencode.vulnhunt.json",
            }
            for relative_path, source in expected.items():
                self.assertEqual(
                    (installed / relative_path).read_text(), source.read_text()
                )

            subprocess.run(
                [str(REPO / "uninstall-opencode.sh")],
                cwd=REPO,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            for relative_path in expected:
                self.assertFalse((installed / relative_path).exists())

    def test_static_profile_denies_execution_and_network(self):
        profile = json.loads(
            (REPO / "opencode" / "opencode.vulnhunt.json").read_text()
        )
        permissions = profile["permission"]
        self.assertEqual(permissions["*"], "deny")
        for tool in ("read", "glob", "grep"):
            self.assertEqual(permissions[tool], "allow")
        self.assertEqual(permissions["external_directory"]["*"], "deny")
        self.assertEqual(permissions["edit"]["*"], "deny")
        self.assertEqual(
            permissions["edit"]["*_VULNHUNT_RESULTS_*/**"], "allow"
        )
        self.assertEqual(
            permissions["edit"]["**/*_VULNHUNT_RESULTS_*/**"], "allow"
        )
        self.assertEqual(permissions["task"]["*"], "deny")
        self.assertEqual(permissions["task"]["vulnhunt-worker"], "allow")
        self.assertFalse(profile["autoupdate"])
        self.assertEqual(profile["share"], "disabled")
        self.assertFalse(profile["formatter"])
        self.assertFalse(profile["lsp"])
        self.assertEqual(profile["plugin"], [])
        self.assertEqual(profile["mcp"], {})

    def test_agents_are_restricted(self):
        orchestrator = (
            REPO / "opencode" / "agents" / "vulnhunt-orchestrator.md"
        ).read_text()
        worker = (
            REPO / "opencode" / "agents" / "vulnhunt-worker.md"
        ).read_text()

        for content in (orchestrator, worker):
            for rule in ('"*": deny', "read: allow", "glob: allow", "grep: allow"):
                self.assertIn(rule, content)
            self.assertIn('"*_VULNHUNT_RESULTS_*/**": allow', content)
            self.assertIn('"**/*_VULNHUNT_RESULTS_*/**": allow', content)

        self.assertIn("vulnhunt-worker: allow", orchestrator)
        for content in (orchestrator, worker):
            self.assertIn("redact the values", content)
            self.assertIn("generated phase", content)

    def test_command_uses_restricted_orchestrator_and_arguments(self):
        command = (REPO / "opencode" / "commands" / "vulnhunt.md").read_text()
        self.assertIn("agent: vulnhunt-orchestrator", command)
        self.assertIn("$ARGUMENTS", command)

        for path in (REPO / "README.md", REPO / "vulnhunt" / "README.md"):
            documented_usage = path.read_text()
            self.assertIn("./run-opencode.sh /path/to/repository", documented_usage)
            self.assertNotIn("--command vulnhunt", documented_usage)

    def test_isolated_launcher_enforces_snapshot_and_artifact_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=source, check=True
            )
            plugin = source / ".OpenCode" / "plugins" / "target.js"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("throw new Error('target plugin loaded')\n")
            for skill_root in (".Agents", ".Claude"):
                skill = source / skill_root / "skills" / "vulnhunt" / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("malicious target skill\n")
            (source / "agents.md").write_text("malicious target instructions\n")
            (source / "claude.md").write_text("malicious target instructions\n")
            (source / "context.md").write_text("malicious target instructions\n")
            copilot = source / ".github" / "copilot-instructions.md"
            copilot.parent.mkdir()
            copilot.write_text("malicious target instructions\n")
            (source / "OpenCode.json").write_text('{"plugin":["target-plugin"]}\n')
            (source / "app.py").write_text("print('target')\n")
            (source / ".GitAttributes").write_text("app.py export-ignore\n")
            for ignore_name in (".GitIgnore", ".Ignore", ".RgIgnore"):
                (source / ignore_name).write_text("app.py\n")
            (source / "src").mkdir()
            (source / "src/app.py").write_text("print('nested')\n")
            (source / "src/.GitAttributes").write_text("app.py export-ignore\n")
            for ignore_name in (".GitIgnore", ".Ignore", ".RgIgnore"):
                (source / "src" / ignore_name).write_text("app.py\n")
            decoy_results = source / "decoy_VULNHUNT_RESULTS_target"
            decoy_results.mkdir()
            (decoy_results / "app.py").write_text("print('must remain read-only')\n")
            os.symlink("app.py", source / "linked.py")
            subprocess.run(["git", "add", "-f", "."], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True
            )
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://x-access-token:secret@github.com/org/repo.git?access_token=also-secret",
                ],
                cwd=source,
                check=True,
            )

            fake_opencode = root / "opencode"
            fake_opencode.write_text(
                """#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path

scenario_path = Path(__file__).with_name("scenario.json")
scenario = json.loads(scenario_path.read_text()) if scenario_path.exists() else {}

if sys.argv[1:] == ["--version"]:
    print("1.18.31")
    raise SystemExit(0)

if sys.argv[1:] == ["run", "--help"]:
    print("--standalone --pure")
    raise SystemExit(0)

workspace = Path.cwd()
assert not (workspace / ".OpenCode/plugins/target.js").exists()
assert not (workspace / ".OpenCode/opencode.json").exists()
assert not (workspace / "OpenCode.json").exists()
assert not (workspace / ".Agents").exists()
assert not (workspace / ".Claude").exists()
assert not (workspace / "agents.md").exists()
assert not (workspace / "claude.md").exists()
assert not (workspace / "context.md").exists()
assert not (workspace / ".github/copilot-instructions.md").exists()
assert not (workspace / ".GitAttributes").exists()
for ignore_name in (".gitignore", ".ignore", ".rgignore"):
    assert (workspace / ignore_name).read_text() == "!**\\n"
assert (workspace / "app.py").read_text() == "print('target')\\n"
assert not (workspace / "src/.GitAttributes").exists()
for ignore_name in (".GitIgnore", ".Ignore", ".RgIgnore"):
    assert not (workspace / "src" / ignore_name).exists()
assert (workspace / "src/app.py").read_text() == "print('nested')\\n"
assert not (workspace / "linked.py").is_symlink()
assert (workspace / "linked.py").read_text() == "symlink target: app.py\\n"
assert (workspace / ".git").is_dir()
assert workspace.stat().st_mode & 0o222 == 0
assert (workspace / "app.py").stat().st_mode & 0o222 == 0
assert (workspace / "decoy_VULNHUNT_RESULTS_target/app.py").stat().st_mode & 0o222 == 0
listed = subprocess.run(
    [str(Path(__file__).with_name("rg")), "--no-config", "--files", "--hidden", "--glob=!**/.git/**"],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()
assert "app.py" in listed
assert "src/app.py" in listed
isolation_root = Path(os.environ["HOME"]).parent
assert Path(os.environ["OPENCODE_CONFIG_DIR"]).resolve() == (
    workspace / ".opencode"
).resolve()
assert Path(os.environ["XDG_CONFIG_HOME"]) == isolation_root / "xdg/config"
assert Path(os.environ["XDG_DATA_HOME"]) == isolation_root / "xdg/data"
assert Path(os.environ["XDG_CACHE_HOME"]) == isolation_root / "xdg/cache"
assert Path(os.environ["XDG_STATE_HOME"]) == isolation_root / "xdg/state"
assert Path(os.environ["XDG_RUNTIME_DIR"]) == isolation_root / "xdg/runtime"
assert Path(os.environ["TMPDIR"]) == isolation_root / "tmp"
assert os.environ["OPENCODE_DISABLE_CLAUDE_CODE"] == "1"
assert os.environ["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "1"
assert os.environ["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] == "1"
assert os.environ["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
assert os.environ["OPENCODE_DISABLE_FFF"] == "1"
assert os.environ["OPENCODE_DISABLE_FILEWATCHER"] == "1"
assert os.environ["OPENCODE_FILEWATCHER_DISABLE"] == "1"
assert os.environ["OPENCODE_DISABLE_LSP_DOWNLOAD"] == "true"
assert os.environ["OPENCODE_DISABLE_SHARE"] == "1"
assert os.environ["OPENCODE_PURE"] == "1"
for poisoned in (
    "RIPGREP_CONFIG_PATH",
    "OPENCODE_PERMISSION",
    "OPENCODE_AUTO_SHARE",
    "OPENCODE_CLI_CONFIG_CONTENT",
    "OPENAI_API_KEY",
):
    assert poisoned not in os.environ
profile = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
assert profile["permission"]["*"] == "deny"
assert profile["share"] == "disabled"
assert profile["lsp"] is False
assert profile["formatter"] is False
match = re.search(r"VULNHUNT_DIR: (.+)", sys.argv[-1])
assert match
assert "secret" not in sys.argv[-1]
assert "Repository URL: https://github.com/org/repo" in sys.argv[-1]
results = Path(match.group(1).strip())
assert results.stat().st_mode & 0o200 != 0
(results / "results").mkdir()
if scenario.get("ZERO_PARTITIONS") == "1":
    (results / "phase1_output.md").write_text("PARTITION_COUNT: 0\\n")
else:
    partition_count = scenario.get("PARTITION_COUNT_OVERRIDE", "2")
    (results / "phase1_output.md").write_text(f"PARTITION_COUNT: {partition_count}\\n")
    (results / "partitions").mkdir()
    (results / "partitions/sg-1_data.md").write_text("REACHABILITY: PRODUCTION\\n")
    (results / "partitions/sg-2_data.md").write_text("REACHABILITY: DEV-ONLY\\n")
    for class_name in ("inj", "nav", "log"):
        if scenario.get("OMIT_RESULT") == class_name:
            continue
        (results / f"results/sg-1_{class_name}_results.md").write_text("# result\\n")
(results / "results/sink_driven_results.md").write_text("# result\\n")
confirmed = int(scenario.get("CONFIRMED_COUNT", "1"))
if scenario.get("OMIT_ARTIFACT") != "phase2b_output.md":
    (results / "phase2b_output.md").write_text(f"CONFIRMED_COUNT: {confirmed}\\n")

if confirmed:
    for artifact in ("phase3_output.md", "phase3d_output.md"):
        if scenario.get("OMIT_ARTIFACT") != artifact:
            (results / artifact).write_text("# phase summary\\n")
    (results / "poc").mkdir()
    (results / "exploit_tests").mkdir()
    finding_id = (
        "VULN-PLATFORM-AUTHN"
        if scenario.get("PLATFORM_ROLLUP") == "1"
        else "VULN-001"
    )
    poc = f"poc/{finding_id}_sql_injection.md"
    test = f"exploit_tests/{finding_id}_exploit_test.py"
    if scenario.get("SYMLINK_POC") == "1":
        os.symlink("../../app.py", results / poc)
    elif scenario.get("OMIT_FINDING_ARTIFACT") != "poc":
        (results / poc).write_text("# poc\\n")
    if scenario.get("OMIT_FINDING_ARTIFACT") != "test":
        (results / test).write_text("# exploit test\\n")
    linked_test = (
        "exploit_tests/missing.py"
        if scenario.get("BROKEN_REPORT_LINK") == "1"
        else test
    )
    report = (
        "# VulnHunter Security Audit Report\\n\\n"
        "| ID | Evidence |\\n|---|---|\\n"
        f"| {finding_id} | [PoC]({poc}) \\\\| [Test]({linked_test}) |\\n"
    )
    if scenario.get("PLATFORM_ROLLUP") == "1":
        report += (
            "\\n- VULN-001 at app.py:1, CWE-306 — "
            "SUBSUMED-BY: VULN-PLATFORM-AUTHN\\n"
        )
    manifest = (
        "FINDING_COUNT: 0\\n"
        if scenario.get("OMIT_MANIFEST_FINDING") == "1"
        else f"FINDING_COUNT: 1\\n{finding_id}|{poc}|{test}\\n"
    )
else:
    report = (
        "# VulnHunter Security Audit Report\\n\\n"
        "No exploitable vulnerabilities found.\\n"
    )
    manifest = "FINDING_COUNT: 0\\n"

if scenario.get("OMIT_ARTIFACT") != "README.md":
    (results / "README.md").write_text(report)
if scenario.get("OMIT_ARTIFACT") != "findings.manifest":
    (results / "findings.manifest").write_text(manifest)
"""
            )
            fake_opencode.chmod(0o755)
            rg = shutil.which("rg")
            self.assertIsNotNone(rg)
            os.symlink(rg, root / "rg")
            scenario = root / "scenario.json"
            scenario.write_text("{}")

            ambient_xdg = root / "ambient-xdg"
            env = os.environ.copy()
            env["OPENCODE_BIN"] = str(fake_opencode)
            env["XDG_CONFIG_HOME"] = str(ambient_xdg)
            env["AMBIENT_XDG"] = str(ambient_xdg)
            env["AMBIENT_HOME"] = env["HOME"]
            for name in ("DATA", "CACHE", "STATE"):
                ambient = root / f"ambient-{name.lower()}"
                ambient.mkdir()
                env[f"XDG_{name}_HOME"] = str(ambient)
                env[f"AMBIENT_XDG_{name}"] = str(ambient)
            ambient_tmp = root / "ambient-tmp"
            ambient_tmp.mkdir()
            (ambient_tmp / ".ignore").write_text("**/app.py\n")
            env["TMPDIR"] = str(ambient_tmp)
            env["AMBIENT_TMPDIR"] = str(ambient_tmp)
            ambient_ripgrep = root / "ambient-ripgreprc"
            ambient_ripgrep.write_text("--glob=!app.py\n")
            env["RIPGREP_CONFIG_PATH"] = str(ambient_ripgrep)
            env["OPENCODE_PERMISSION"] = '{"bash":"allow"}'
            env["OPENCODE_AUTO_SHARE"] = "true"
            env["OPENCODE_CLI_CONFIG_CONTENT"] = '{"permission":{"bash":"allow"}}'
            env["OPENAI_API_KEY"] = "must-not-reach-opencode"

            def run_scenario(settings):
                scenario.write_text(json.dumps(settings))
                return subprocess.run(
                    [str(REPO / "run-opencode.sh"), str(source)],
                    cwd=REPO,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            completed = run_scenario({})
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            report = re.search(r"^Report: (.+)$", completed.stdout, re.MULTILINE)
            self.assertIsNotNone(report)
            self.assertIn("VULN-001", Path(report.group(1)).read_text())

            rollup = run_scenario({"PLATFORM_ROLLUP": "1"})
            self.assertEqual(rollup.returncode, 0, rollup.stdout + rollup.stderr)

            failure_cases = (
                ({"OMIT_RESULT": "nav"}, "missing scan result: sg-1_nav_results.md"),
                (
                    {"PARTITION_COUNT_OVERRIDE": "3"},
                    "expected 3 partition files, found 2",
                ),
                (
                    {"OMIT_ARTIFACT": "phase2b_output.md"},
                    "missing scan output: phase2b_output.md",
                ),
                (
                    {"OMIT_FINDING_ARTIFACT": "poc"},
                    "missing finding artifact: poc/VULN-001_sql_injection.md",
                ),
                (
                    {"SYMLINK_POC": "1"},
                    "missing finding artifact: poc/VULN-001_sql_injection.md",
                ),
                (
                    {"OMIT_MANIFEST_FINDING": "1"},
                    "README finding missing from manifest: VULN-001",
                ),
                (
                    {"BROKEN_REPORT_LINK": "1"},
                    "README.md does not link finding artifact: "
                    "exploit_tests/VULN-001_exploit_test.py",
                ),
            )
            for settings, expected_error in failure_cases:
                with self.subTest(settings=settings):
                    failed = run_scenario(settings)
                    self.assertEqual(failed.returncode, 1)
                    self.assertIn(expected_error, failed.stderr)

            empty = run_scenario({"ZERO_PARTITIONS": "1", "CONFIRMED_COUNT": "0"})
            self.assertEqual(empty.returncode, 0, empty.stdout + empty.stderr)

    def test_launcher_does_not_execute_target_git_fsmonitor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=source, check=True
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-q", "-m", "fixture"],
                cwd=source,
                check=True,
            )
            marker = root / "fsmonitor-executed"
            hook = root / "fsmonitor.sh"
            hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            hook.chmod(0o755)
            subprocess.run(
                ["git", "config", "core.fsmonitor", str(hook)],
                cwd=source,
                check=True,
            )
            fake_opencode = root / "opencode"
            fake_opencode.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = --version ]; then echo 1.18.31; exit 0; fi\n"
                "exit 1\n"
            )
            fake_opencode.chmod(0o755)
            completed = subprocess.run(
                [str(REPO / "run-opencode.sh"), str(source)],
                cwd=REPO,
                env={**os.environ, "OPENCODE_BIN": str(fake_opencode)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(marker.exists())

    def test_launcher_rejects_unsupported_opencode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=source,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=source, check=True
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-q", "-m", "fixture"],
                cwd=source,
                check=True,
            )
            fake_opencode = root / "opencode"
            fake_opencode.write_text("#!/bin/sh\necho 1.18.30\n")
            fake_opencode.chmod(0o755)
            completed = subprocess.run(
                [str(REPO / "run-opencode.sh"), str(source)],
                cwd=source,
                env={**os.environ, "OPENCODE_BIN": str(fake_opencode)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("OpenCode 1.18.31 or later is required", completed.stderr)

    def test_isolated_launcher_rejects_unmaterialized_git_content(self):
        cases = {
            "submodule": "repositories with submodules are not supported",
            "lfs": "repositories with Git LFS pointers are not supported",
        }
        for case, expected_error in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / "source"
                source.mkdir()
                subprocess.run(["git", "init", "-q"], cwd=source, check=True)
                subprocess.run(
                    ["git", "config", "user.email", "test@example.com"],
                    cwd=source,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Test"],
                    cwd=source,
                    check=True,
                )
                (source / "app.py").write_text("print('target')\n")
                subprocess.run(["git", "add", "."], cwd=source, check=True)
                subprocess.run(
                    ["git", "commit", "-q", "-m", "fixture"],
                    cwd=source,
                    check=True,
                )

                if case == "submodule":
                    child = Path(temporary) / "child"
                    child.mkdir()
                    subprocess.run(["git", "init", "-q"], cwd=child, check=True)
                    subprocess.run(
                        [
                            "git",
                            "config",
                            "user.email",
                            "test@example.com",
                        ],
                        cwd=child,
                        check=True,
                    )
                    subprocess.run(
                        ["git", "config", "user.name", "Test"],
                        cwd=child,
                        check=True,
                    )
                    (child / "library.py").write_text("print('library')\n")
                    subprocess.run(["git", "add", "."], cwd=child, check=True)
                    subprocess.run(
                        ["git", "commit", "-q", "-m", "child"],
                        cwd=child,
                        check=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "-c",
                            "protocol.file.allow=always",
                            "submodule",
                            "add",
                            "-q",
                            str(child),
                            "vendor/module",
                        ],
                        cwd=source,
                        check=True,
                    )
                else:
                    (source / "asset.bin").write_text(
                        "version https://git-lfs.github.com/spec/v1\n"
                        "oid sha256:0123456789abcdef\nsize 1\n"
                    )
                    subprocess.run(["git", "add", "asset.bin"], cwd=source, check=True)

                subprocess.run(
                    ["git", "commit", "-q", "-m", case], cwd=source, check=True
                )
                fake_opencode = Path(temporary) / "opencode"
                fake_opencode.write_text(
                    "#!/bin/sh\n"
                    "if [ \"$1\" = --version ]; then echo 1.18.31; exit 0; fi\n"
                    "exit 1\n"
                )
                fake_opencode.chmod(0o755)
                env = os.environ.copy()
                env["OPENCODE_BIN"] = str(fake_opencode)
                completed = subprocess.run(
                    [str(REPO / "run-opencode.sh"), str(source)],
                    cwd=REPO,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 1)
                self.assertIn(expected_error, completed.stderr)

    def test_phase2_workers_run_in_the_foreground(self):
        phase2 = (REPO / "vulnhunt" / "phases" / "phase2_hunt.md").read_text()
        skill = (REPO / "vulnhunt" / "SKILL.md").read_text()
        normalized = " ".join(phase2.split())
        self.assertIn("Run every agent synchronously in the foreground", normalized)
        self.assertIn("Never request a background task", normalized)
        self.assertNotIn("parallel trace agents", phase2)
        self.assertNotIn("In parallel with trace agents", phase2)
        self.assertIn("results/sink_driven_results.md", phase2)
        self.assertIn("Do not return until the file exists", phase2)
        self.assertIn("REACHABILITY: PRODUCTION", phase2)
        self.assertIn("REACHABILITY: DEV-ONLY", phase2)
        self.assertIn("production_partition_count", phase2)
        self.assertIn("production_partition_count", skill)
        self.assertIn("PARTITION_COUNT: N", skill)
        phase1 = (REPO / "vulnhunt" / "phases" / "phase1_recon.md").read_text()
        self.assertIn("PARTITION_COUNT: 0", phase1)

    def test_core_scanner_has_no_claude_runtime_contracts(self):
        forbidden = {
            "${CLAUDE_SKILL_DIR}": "Claude-only phase resolution",
            "`/cost": "Claude-only cost command",
            "`/model": "Claude-only model command",
            "general-purpose": "unrestricted Claude agent type",
            "Bash is AVAILABLE": "Bash-enabled execution mode",
        }
        for path in CORE_FILES:
            content = path.read_text()
            for token, reason in forbidden.items():
                self.assertNotIn(token, content, f"{path}: {reason}")

    def test_reporting_preserves_all_reportable_severities(self):
        phase3 = (
            REPO / "vulnhunt" / "phases" / "phase3_reproduce_test.md"
        ).read_text()
        phase4 = (
            REPO / "vulnhunt" / "phases" / "phase4_report.md"
        ).read_text()
        self.assertIn("High+, High, and Medium severity", phase3)
        self.assertIn("High+ + High + Medium CONFIRMED", phase3)
        self.assertIn("Severity is immutable at this stage", phase4)
        self.assertIn("`High+` must remain `High+`", phase4)
        self.assertIn("File creation is mandatory", phase4)
        self.assertIn("do not print the report body as the chat response", phase4)
        self.assertIn("read the beginning of that path", phase4)
        self.assertIn("copy artifact filenames exactly", phase4)
        self.assertIn("read every local artifact path linked by the README", phase4)


if __name__ == "__main__":
    unittest.main()
