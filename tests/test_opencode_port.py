import json
import os
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
            env["XDG_CONFIG_HOME"] = config_home
            subprocess.run(
                [str(REPO / "install-opencode.sh")],
                cwd=REPO,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            installed = Path(config_home) / "opencode"
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
        for tool in ("bash", "webfetch", "websearch", "lsp", "question"):
            self.assertEqual(permissions[tool], "deny")
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
            for rule in (
                "bash: deny",
                "webfetch: deny",
                "websearch: deny",
                "lsp: deny",
            ):
                self.assertIn(rule, content)
            self.assertIn('"*_VULNHUNT_RESULTS_*/**": allow', content)
            self.assertIn('"**/*_VULNHUNT_RESULTS_*/**": allow', content)

        self.assertIn("vulnhunt-worker: allow", orchestrator)
        self.assertIn("task: deny", worker)
        self.assertIn("skill: deny", worker)

    def test_command_uses_restricted_orchestrator_and_arguments(self):
        command = (REPO / "opencode" / "commands" / "vulnhunt.md").read_text()
        self.assertIn("agent: vulnhunt-orchestrator", command)
        self.assertIn("$ARGUMENTS", command)

        for path in (
            REPO / "README.md",
            REPO / "vulnhunt" / "README.md",
            REPO / "install-opencode.sh",
            REPO / "install-opencode.cmd",
        ):
            documented_usage = path.read_text()
            self.assertIn("--agent vulnhunt-orchestrator", documented_usage)
            self.assertNotIn("--command vulnhunt", documented_usage)

    def test_phase2_workers_run_in_the_foreground(self):
        phase2 = (REPO / "vulnhunt" / "phases" / "phase2_hunt.md").read_text()
        normalized = " ".join(phase2.split())
        self.assertIn("Run every agent synchronously in the foreground", normalized)
        self.assertIn("Never request a background task", normalized)
        self.assertNotIn("parallel trace agents", phase2)
        self.assertNotIn("In parallel with trace agents", phase2)

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
