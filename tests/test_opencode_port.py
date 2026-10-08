import json
import os
import re
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

    def test_command_uses_restricted_orchestrator_and_arguments(self):
        command = (REPO / "opencode" / "commands" / "vulnhunt.md").read_text()
        self.assertIn("agent: vulnhunt-orchestrator", command)
        self.assertIn("$ARGUMENTS", command)

        for path in (REPO / "README.md", REPO / "vulnhunt" / "README.md"):
            documented_usage = path.read_text()
            self.assertIn("./run-opencode.sh /path/to/repository", documented_usage)
            self.assertNotIn("--command vulnhunt", documented_usage)

    def test_isolated_launcher_uses_trusted_snapshot_and_config(self):
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
            plugin = source / ".opencode" / "plugins" / "target.js"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("throw new Error('target plugin loaded')\n")
            (source / "opencode.json").write_text('{"plugin":["target-plugin"]}\n')
            (source / "app.py").write_text("print('target')\n")
            (source / ".gitattributes").write_text("app.py export-ignore\n")
            (source / "src").mkdir()
            (source / "src/app.py").write_text("print('nested')\n")
            (source / "src/.gitattributes").write_text("app.py export-ignore\n")
            os.symlink("app.py", source / "linked.py")
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True
            )

            fake_opencode = root / "opencode"
            fake_opencode.write_text(
                """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if sys.argv[1:] == ["run", "--help"]:
    print("--standalone --pure")
    raise SystemExit(0)

workspace = Path.cwd()
assert not (workspace / ".opencode/plugins/target.js").exists()
assert not (workspace / "opencode.json").exists()
assert not (workspace / ".gitattributes").exists()
assert (workspace / "app.py").read_text() == "print('target')\\n"
assert not (workspace / "src/.gitattributes").exists()
assert (workspace / "src/app.py").read_text() == "print('nested')\\n"
assert not (workspace / "linked.py").is_symlink()
assert (workspace / "linked.py").read_text() == "symlink target: app.py\\n"
assert Path(os.environ["OPENCODE_CONFIG_DIR"]).resolve() == (workspace / ".opencode").resolve()
assert os.environ["XDG_CONFIG_HOME"] != os.environ["AMBIENT_XDG"]
assert os.environ["HOME"] != os.environ["AMBIENT_HOME"]
profile = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
assert profile["permission"]["*"] == "deny"
match = re.search(r"VULNHUNT_DIR: (.+)", sys.argv[-1])
assert match
results = Path(match.group(1).strip())
(results / "partitions").mkdir()
(results / "results").mkdir()
(results / "partitions/sg-1_data.md").write_text("REACHABILITY: PRODUCTION\\n")
(results / "partitions/sg-2_data.md").write_text("REACHABILITY: DEV-ONLY\\n")
for class_name in ("inj", "nav", "log"):
    if os.environ.get("OMIT_RESULT") == class_name:
        continue
    (results / f"results/sg-1_{class_name}_results.md").write_text("# result\\n")
(results / "results/sink_driven_results.md").write_text("# result\\n")
(results / "README.md").write_text("# report\\n")
"""
            )
            fake_opencode.chmod(0o755)

            ambient_xdg = root / "ambient-xdg"
            env = os.environ.copy()
            env["OPENCODE_BIN"] = str(fake_opencode)
            env["XDG_CONFIG_HOME"] = str(ambient_xdg)
            env["AMBIENT_XDG"] = str(ambient_xdg)
            env["AMBIENT_HOME"] = env["HOME"]
            completed = subprocess.run(
                [str(REPO / "run-opencode.sh"), str(source)],
                cwd=REPO,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            report = re.search(r"^Report: (.+)$", completed.stdout, re.MULTILINE)
            self.assertIsNotNone(report)
            self.assertEqual(Path(report.group(1)).read_text(), "# report\n")

            env["OMIT_RESULT"] = "nav"
            incomplete = subprocess.run(
                [str(REPO / "run-opencode.sh"), str(source)],
                cwd=REPO,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(incomplete.returncode, 1)
            self.assertIn("missing scan result: sg-1_nav_results.md", incomplete.stderr)

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
                env = os.environ.copy()
                env["OPENCODE_BIN"] = "false"
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
