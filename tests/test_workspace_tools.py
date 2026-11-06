"""Política de permisos del Developer: concedido dentro del workspace, el resto se pregunta."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from crew.workspace_tools import AccessError, WorkspaceAccess, build_tools, is_sensitive_name


class Asker:
    """Responde en orden y registra cada pregunta."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.questions = []

    def __call__(self, question):
        self.questions.append(question)
        return self.answers.pop(0) if self.answers else "n"


class WorkspaceAccessTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root = base / "workspace"
        self.root.mkdir()
        self.outside = base / "outside"
        self.outside.mkdir()

    def access(self, *answers):
        self.ask = Asker(*answers)
        return WorkspaceAccess(self.root, self.ask)

    def test_read_write_edit_and_delete_inside_workspace_never_ask(self):
        access = self.access()
        access.write_file("api/src/App.java", "class App {\n  int a;\n}\n")
        self.assertIn("class App", access.read_file("api/src/App.java"))
        access.replace_in_file("api/src/App.java", "int a;", "int b;")
        self.assertIn("int b;", (self.root / "api/src/App.java").read_text())
        self.assertIn("api/src/App.java", access.list_files("api", recursive=True))
        self.assertIn("App.java:2", access.search_text("int b"))
        access.delete_path("api/src/App.java")
        self.assertFalse((self.root / "api/src/App.java").exists())
        self.assertEqual(self.ask.questions, [])

    def test_replace_requires_exactly_one_match_and_keeps_crlf(self):
        access = self.access()
        (self.root / "a.txt").write_bytes(b"x\r\nx\r\n")
        with self.assertRaisesRegex(AccessError, "2 veces"):
            access.replace_in_file("a.txt", "x", "y")
        (self.root / "b.txt").write_bytes(b"one\r\ntwo\r\n")
        access.replace_in_file("b.txt", "one\ntwo", "one\nthree")
        self.assertEqual((self.root / "b.txt").read_bytes(), b"one\r\nthree\r\n")

    def test_path_outside_workspace_asks_and_denial_leaves_no_trace(self):
        access = self.access("n")
        target = self.outside / "leak.txt"
        with self.assertRaises(AccessError) as denied:
            access.write_file(str(target), "data")
        self.assertTrue(denied.exception.denied)
        self.assertFalse(target.exists())
        self.assertEqual(len(self.ask.questions), 1)
        self.assertIn("fuera del workspace", self.ask.questions[0])

    def test_traversal_and_absolute_paths_are_treated_as_outside(self):
        access = self.access("n", "n")
        with self.assertRaises(AccessError):
            access.read_file("../outside/x.txt")
        with self.assertRaises(AccessError):
            access.delete_path(str(self.outside))
        self.assertEqual(len(self.ask.questions), 2)

    def test_approve_once_asks_again_but_approve_always_remembers(self):
        access = self.access("s", "s", "a")
        for name in ("one.txt", "two.txt"):
            access.write_file(str(self.outside / name), "x")
        self.assertEqual(len(self.ask.questions), 2)
        access.write_file(str(self.outside / "three.txt"), "x")
        access.write_file(str(self.outside / "four.txt"), "x")
        self.assertEqual(len(self.ask.questions), 3)
        self.assertTrue((self.outside / "four.txt").exists())

    def test_sensitive_files_ask_but_ordinary_token_names_do_not(self):
        access = self.access("n")
        with self.assertRaises(AccessError):
            access.write_file(".env", "KEY=1")
        self.assertFalse((self.root / ".env").exists())
        access.write_file("src/TokenService.java", "class TokenService {}")
        self.assertEqual(len(self.ask.questions), 1)
        self.assertTrue(is_sensitive_name(".env.local"))
        self.assertTrue(is_sensitive_name("server.pem"))
        self.assertFalse(is_sensitive_name("TokenService.java"))

    def test_git_metadata_is_never_accessible_and_never_asks(self):
        (self.root / ".git").mkdir()
        access = self.access("s")
        for action in (lambda: access.write_file(".git/config", "x"), lambda: access.read_file(".GIT/HEAD"),
                       lambda: access.delete_path(".git", recursive=True)):
            with self.assertRaisesRegex(AccessError, "git"):
                action()
        self.assertEqual(self.ask.questions, [])

    def test_directory_delete_rules(self):
        access = self.access("n", "s")
        (self.root / "empty").mkdir()
        access.delete_path("empty")
        self.assertFalse((self.root / "empty").exists())
        (self.root / "full").mkdir()
        (self.root / "full/a.txt").write_text("x")
        with self.assertRaisesRegex(AccessError, "recursive"):
            access.delete_path("full")
        with self.assertRaises(AccessError):
            access.delete_path("full", recursive=True)
        self.assertTrue((self.root / "full/a.txt").exists())
        access.delete_path("full", recursive=True)
        self.assertFalse((self.root / "full").exists())
        with self.assertRaisesRegex(AccessError, "ra\u00edz"):
            access.delete_path(".")

    def test_commands_ask_per_program_and_run_without_a_shell(self):
        access = self.access("s", "a")
        result = access.run_command(sys.executable, ["-c", "print('hola')"])
        self.assertIn("C\u00f3digo de salida: 0", result)
        self.assertIn("hola", result)
        self.assertIn("-c", self.ask.questions[0])
        access.run_command(sys.executable, ["-c", "print(1)"])
        access.run_command(sys.executable, ["-c", "print(2)"])
        self.assertEqual(len(self.ask.questions), 2)

    def test_denied_command_does_not_run_and_publishers_and_shells_are_blocked(self):
        marker = self.root / "ran.txt"
        access = self.access("n")
        with self.assertRaises(AccessError):
            access.run_command(sys.executable, ["-c", f"open(r'{marker}', 'w').write('x')"])
        self.assertFalse(marker.exists())
        for blocked in ("git", "gh", "powershell", "cmd", "bash"):
            with self.assertRaises(AccessError) as error:
                access.run_command(blocked, ["x"])
            self.assertTrue(error.exception.denied, blocked)
        self.assertEqual(len(self.ask.questions), 1)

    def test_command_environment_hides_secrets(self):
        import os
        os.environ["CREWAI_TEST_API_KEY"] = "super-secret"
        self.addCleanup(os.environ.pop, "CREWAI_TEST_API_KEY", None)
        access = self.access("s")
        result = access.run_command(sys.executable, ["-c", "import os;print(os.environ.get('CREWAI_TEST_API_KEY'))"])
        self.assertIn("None", result)
        self.assertNotIn("super-secret", result)


class ToolWrapperTests(unittest.TestCase):
    def test_denial_is_reported_to_the_model_as_a_denied_result_and_success_as_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ws"
            root.mkdir()
            outside = Path(tmp) / "outside.txt"
            tools = {tool.name: tool for tool in build_tools(WorkspaceAccess(root, Asker("n")))}
            invocation = lambda name, **arguments: type(
                "Inv", (), {"arguments": arguments, "session_id": "", "tool_call_id": "", "tool_name": name,
                            "available_tools": None, "agent_id": None, "request_id": None})()
            denied = asyncio.run(tools["write_file"].handler(invocation("write_file", path=str(outside), content="x")))
            self.assertEqual(denied.result_type, "denied")
            self.assertIn("denegó", denied.text_result_for_llm)
            self.assertFalse(outside.exists())
            ok = asyncio.run(tools["write_file"].handler(invocation("write_file", path="a.txt", content="hi")))
            self.assertEqual(ok.result_type, "success")
            self.assertTrue((root / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
