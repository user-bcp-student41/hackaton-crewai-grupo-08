"""Contrato del agente de desarrollo Full Stack y de sus herramientas."""

import tempfile
import unittest

from agents import developer
from crew.copilot_llm import AgenticCopilotLLM

TOOLS = ["list_files", "read_file", "search_text", "write_file", "replace_in_file", "delete_path", "run_command"]


class DeveloperTests(unittest.TestCase):
    def test_task_includes_feature_and_implementation_context(self):
        feature = {
            "title": "Crear cuenta",
            "description": "Registrar una cuenta desde Angular.",
            "acceptance_criteria": ["La API responde 201"],
        }
        task = developer.build_task(
            feature,
            workspace_path="workspaces/issue-14",
            project_context="src/main/java/ExistingResource.java",
            architecture_context="POST /accounts devuelve 201.",
            prior_decisions="La HU 12 define el formato del identificador.",
        )
        self.assertIs(task.agent, developer.agent)
        for expected in (
            "Crear cuenta", "La API responde 201", "Java 21", "imperativo", "Angular",
            "workspaces/issue-14", "ExistingResource.java", "POST /accounts", "HU 12",
            "write_file", "replace_in_file", "delete_path", "denegó un permiso",
        ):
            self.assertIn(expected, task.description)

    def test_attach_workspace_binds_every_tool_to_the_agent_llm(self):
        self.assertIsInstance(developer.agent.llm, AgenticCopilotLLM)
        with tempfile.TemporaryDirectory() as tmp:
            access = developer.attach_workspace(tmp, lambda question: "n")
            self.assertEqual([tool.name for tool in developer.agent.llm.session_tools], TOOLS)
            self.assertEqual(developer.agent.llm.session_directory, str(access.root))
            self.assertTrue(all(tool.skip_permission for tool in developer.agent.llm.session_tools))
        developer.agent.llm.bind([], "")


if __name__ == "__main__":
    unittest.main()