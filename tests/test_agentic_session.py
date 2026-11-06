"""Sesión del SDK con herramientas propias y LLM del Developer, sin llamar a Copilot."""

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from copilot.session_events import AssistantMessageData

from crew import copilot_llm, devops
from crew.copilot_llm import AgenticCopilotLLM, CopilotLLM
from crew.workspace_tools import WorkspaceAccess, build_tools
from lab_copilot import runtime


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_and_wait(self, prompt, timeout=None):
        event = MagicMock()
        event.data = MagicMock(spec=AssistantMessageData)
        event.data.content = "listo"
        return event


class FakeClient:
    created = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def create_session(self, **kwargs):
        FakeClient.created.append(kwargs)
        return FakeSession()


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeClient.created = []

    def complete(self, **options):
        with patch.object(runtime.copilot, "CopilotClient", FakeClient):
            return asyncio.run(runtime.complete("hola", "modelo", 5, **options)), FakeClient.created[-1]

    def test_default_session_stays_text_only(self):
        text, session = self.complete()
        self.assertEqual(text, "listo")
        self.assertEqual(session["available_tools"], [])
        self.assertNotIn("tools", session)

    def test_tools_are_registered_and_native_ones_stay_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = build_tools(WorkspaceAccess(tmp, lambda question: "n"))
            _, session = self.complete(tools=tools, working_directory=tmp, system_message="usa herramientas")
        self.assertEqual(session["tools"], tools)
        self.assertEqual(session["available_tools"], [f"custom:{tool.name}" for tool in tools])
        self.assertEqual(session["working_directory"], tmp)
        self.assertEqual(session["system_message"]["content"], "usa herramientas")


class AgenticLlmTests(unittest.TestCase):
    def test_without_bound_tools_it_behaves_like_the_text_only_llm(self):
        llm = AgenticCopilotLLM(model="m")
        with patch.object(CopilotLLM, "call", return_value="texto") as parent:
            self.assertEqual(llm.call("hola"), "texto")
        parent.assert_called_once()

    def test_with_bound_tools_the_session_gets_them_and_the_workspace(self):
        llm = AgenticCopilotLLM(model="m")
        llm.bind(["tool"], "C:/ws")
        captured = {}

        async def fake_complete(prompt, model, timeout, **options):
            captured.update(options, prompt=prompt, timeout=timeout)
            return "ok"

        with patch.object(copilot_llm, "_complete", fake_complete):
            self.assertEqual(llm.call("hola"), "ok")
        self.assertEqual(captured["tools"], ["tool"])
        self.assertEqual(captured["working_directory"], "C:/ws")
        self.assertIn("herramientas", captured["system_message"])
        self.assertGreaterEqual(captured["timeout"], 1800)

    def test_crewai_native_tools_are_still_rejected(self):
        llm = AgenticCopilotLLM(model="m")
        llm.bind(["tool"], "C:/ws")
        with self.assertRaises(ValueError):
            llm.call("hola", tools=[{"name": "x"}])


class WorkspaceChangesTests(unittest.TestCase):
    def git(self, root, *args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    def test_detects_created_edited_and_deleted_files_and_skips_build_and_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.email", "t@example.com")
            self.git(root, "config", "user.name", "t")
            (root / "keep.txt").write_text("a")
            (root / "edit.txt").write_text("a")
            (root / "gone.txt").write_text("a")
            self.git(root, "add", ".")
            self.git(root, "commit", "-qm", "base")

            (root / "edit.txt").write_text("b")
            (root / "gone.txt").unlink()
            (root / "api/src").mkdir(parents=True)
            (root / "api/src/New.java").write_text("class New {}")
            (root / "api/src/TokenService.java").write_text("class T {}")
            (root / "target").mkdir()
            (root / "target/out.class").write_text("x")
            (root / ".env").write_text("KEY=1")

            self.assertEqual(
                devops.workspace_changes(root),
                ["api/src/New.java", "api/src/TokenService.java", "edit.txt", "gone.txt"],
            )


if __name__ == "__main__":
    unittest.main()
