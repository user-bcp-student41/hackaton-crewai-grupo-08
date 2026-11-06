"""DevOps publica dos PR sin llamar a git, gh ni a la red."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crew import devops

FEATURE = {"title": "Transfer funds", "description": "d", "acceptance_criteria": []}
APPROVED = "Todo coherente.\nVEREDICTO: APROBADO"


class DevopsTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.clone = None
        self.staged = {}

    def fake_run(self, cmd, cwd=None):
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "repo", "clone"]:
            self.clone = Path(cmd[4])
            self.clone.mkdir(parents=True)
        if cmd[:2] == ["git", "add"]:
            self.staged[cmd[-1]] = sorted(
                p.relative_to(self.clone).as_posix() for p in (self.clone / cmd[-1]).rglob("*") if p.is_file()
            )
        if cmd[:3] == ["gh", "repo", "view"]:
            return "main"
        if cmd[:2] == ["git", "status"]:
            return "A  changed"
        if cmd[:3] == ["gh", "pr", "create"]:
            return "https://github.com/acme/ai-labs/pull/" + str(len([c for c in self.calls if c[:3] == cmd[:3]]))
        return ""

    def output(self, tmp):
        out = Path(tmp) / "output"
        (out / "specs").mkdir(parents=True, exist_ok=True)
        (out / "specs/backend_spec.md").write_text("backend spec", encoding="utf-8")
        (out / "backend-quarkus/src").mkdir(parents=True, exist_ok=True)
        (out / "backend-quarkus/src/A.java").write_text("class A {}", encoding="utf-8")
        (out / "backend-quarkus/target").mkdir(exist_ok=True)
        (out / "backend-quarkus/target/skip.class").write_text("x", encoding="utf-8")
        (out / "frontend-angular/src").mkdir(parents=True, exist_ok=True)
        (out / "frontend-angular/src/a.ts").write_text("export {}", encoding="utf-8")
        return out

    def publish(self, tmp, chapter=APPROVED, published=None, answer="s", repo="acme/ai-labs"):
        env = {"AI_LABS_REPO": repo}
        with patch.dict("os.environ", env), patch.object(devops, "_run", side_effect=self.fake_run), \
                contextlib.redirect_stdout(io.StringIO()):
            return devops.publish(self.output(tmp), FEATURE, chapter, published, confirm=lambda _: answer)

    def test_verdict_parsing(self):
        self.assertEqual(devops.chapter_verdict("VEREDICTO: APROBADO"), "APROBADO")
        self.assertEqual(devops.chapter_verdict("**VEREDICTO:** APROBADO"), "APROBADO")
        self.assertEqual(devops.chapter_verdict("VEREDICTO: RECHAZADO"), "RECHAZADO")
        self.assertEqual(devops.chapter_verdict("VEREDICTO: APROBADO\nVEREDICTO: RECHAZADO"), "RECHAZADO")
        self.assertEqual(devops.chapter_verdict("sin veredicto"), "")

    def test_opens_one_pr_per_target_with_expected_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            published = self.publish(tmp)
            self.assertEqual(set(published), {"backend", "frontend"})
            self.assertEqual(self.staged, {"api": ["api/src/A.java"], "web": ["web/src/a.ts"]})
            adds = [c for c in self.calls if c[:2] == ["git", "add"]]
            self.assertEqual([c[-1] for c in adds], ["api", "web"])
            self.assertEqual(len([c for c in self.calls if c[:3] == ["gh", "pr", "create"]]), 2)

    def test_verdict_is_optional_and_human_confirmation_decides(self):
        for chapter in ("sin veredicto", "VEREDICTO: RECHAZADO"):
            with tempfile.TemporaryDirectory() as tmp:
                self.calls.clear()
                self.assertEqual(set(self.publish(tmp, chapter=chapter)), {"backend", "frontend"})
                body = next(c[c.index("--body") + 1] for c in self.calls if c[:3] == ["gh", "pr", "create"])
                self.assertIn("RECHAZADO" if "RECHAZADO" in chapter else "no emitió veredicto", body)

    def test_does_nothing_without_repo_or_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.publish(tmp, repo=""), {})
            self.assertEqual(self.publish(tmp, repo="no es un repo"), {})
            self.assertEqual(self.publish(tmp, answer="n"), {})
            self.assertEqual(self.calls, [])

    def test_skips_targets_already_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = {"backend": "https://github.com/acme/ai-labs/pull/9"}
            published = self.publish(tmp, published=done)
            self.assertEqual(published["backend"], done["backend"])
            self.assertIn("frontend", published)
            adds = [c for c in self.calls if c[:2] == ["git", "add"]]
            self.assertEqual([c[-1] for c in adds], ["web"])

    def test_default_confirmation_reads_input_at_call_time(self):
        with tempfile.TemporaryDirectory() as tmp, patch("builtins.input", return_value="n"), \
                patch.dict("os.environ", {"AI_LABS_REPO": "acme/ai-labs"}), \
                patch.object(devops, "_run", side_effect=self.fake_run), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(devops.publish(self.output(tmp), FEATURE, APPROVED, {}), {})
            self.assertEqual(self.calls, [])

    def test_invalid_activation_is_rejected(self):
        with patch.dict("os.environ", {"CREWAI_PUBLISH_PRS": "maybe"}):
            with self.assertRaises(ValueError):
                devops.enabled()


class FeatureWorkspaceTests(unittest.TestCase):
    FEATURE = {"title": "Crear cuenta", "issue_number": 14}

    def test_prepare_workspace_clones_and_creates_local_feature_branch(self):
        calls = []
        current_branch = [""]

        def fake_run(cmd, cwd=None):
            calls.append((cmd, cwd))
            if cmd[:3] == ["gh", "repo", "clone"]:
                clone = Path(cmd[4])
                (clone / ".git").mkdir(parents=True)
            elif cmd[:3] == ["git", "switch", "main"]:
                current_branch[0] = "main"
            elif cmd[:3] == ["git", "switch", "-c"]:
                current_branch[0] = cmd[3]
            elif cmd[:3] == ["git", "branch", "--show-current"]:
                return current_branch[0]
            return ""

        with tempfile.TemporaryDirectory() as tmp, patch.object(devops, "_run", side_effect=fake_run):
            workspace = devops.prepare_workspace(self.FEATURE, Path(tmp), "user/repo", "main")
            resumed = devops.prepare_workspace(self.FEATURE, Path(tmp), "user/repo", "main")

        self.assertEqual(workspace, resumed)
        self.assertEqual(devops.feature_branch(self.FEATURE), "feature/14-crear-cuenta")
        switches = [cmd for cmd, _ in calls if cmd[:2] == ["git", "switch"]]
        self.assertEqual(switches, [
            ["git", "switch", "main"], ["git", "switch", "-c", "feature/14-crear-cuenta"],
        ])
        self.assertFalse(any(cmd[:2] == ["git", "push"] for cmd, _ in calls))

    def test_apply_workspace_changes_accepts_relative_paths_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            saved = devops.apply_workspace_changes(
                "// path: src/main/java/AccountResource.java\n```java\nclass AccountResource {}\n```",
                workspace,
            )
            self.assertEqual(saved, ["src/main/java/AccountResource.java"])
            self.assertTrue((workspace / saved[0]).is_file())
            with self.assertRaises(ValueError):
                devops.apply_workspace_changes(
                    "// path: ../outside.java\n```java\nclass Outside {}\n```", workspace
                )
            with self.assertRaises(ValueError):
                devops.apply_workspace_changes(
                    "// path: .GIT/config\n```text\nmodified\n```", workspace
                )

    def test_create_feature_pr_stages_only_approved_files_and_targets_main(self):
        calls = []

        def fake_run(cmd, cwd=None):
            calls.append(cmd)
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return "feature/14-crear-cuenta"
            if cmd[:2] == ["git", "status"]:
                return "A  src/main/java/AccountResource.java"
            if cmd[:3] == ["gh", "pr", "create"]:
                return "https://github.com/user/repo/pull/9"
            return ""

        with tempfile.TemporaryDirectory() as tmp, patch.object(devops, "_run", side_effect=fake_run):
            url = devops.create_feature_pr(
                Path(tmp), self.FEATURE, ["src/main/java/AccountResource.java"], "user/repo", "main"
            )

        self.assertEqual(url, "https://github.com/user/repo/pull/9")
        add = next(command for command in calls if command[:2] == ["git", "add"])
        self.assertEqual(add[-1], "src/main/java/AccountResource.java")
        pr = next(command for command in calls if command[:3] == ["gh", "pr", "create"])
        self.assertEqual(pr[pr.index("--base") + 1], "main")

    def test_create_feature_pr_refuses_pre_staged_changes(self):
        def fake_run(cmd, cwd=None):
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return "feature/14-crear-cuenta"
            if cmd[:4] == ["git", "diff", "--cached", "--name-only"]:
                return "unrelated.txt"
            return ""

        with tempfile.TemporaryDirectory() as tmp, patch.object(devops, "_run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "staged ajenos"):
                devops.create_feature_pr(
                    Path(tmp), self.FEATURE, ["src/main/java/AccountResource.java"], "user/repo", "main"
                )


if __name__ == "__main__":
    unittest.main()
