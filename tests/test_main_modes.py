"""Selector y flujos nuevos sin llamadas a MCP, modelos o GitHub."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main as app

PLAN = """# Plan
# 1\\. Alcance
Contexto general del plan.

### Fuera del alcance
* Despliegue multipaís.

# 2\\. Roles

## 4.1 HU-01 — Registro y activación

|ID|Criterio de aceptación de HU-01|Cómo lo probaremos|Evidencia|
|-|-|-|-|
|HU1-AC1|El onboarding muestra el paso actual.|Avanzar paso por paso.|Captura.|

## 4.2 HU-02 — Confirmación de pagos

|ID|Criterio de aceptación de HU-02|Cómo lo probaremos|Evidencia|
|-|-|-|-|
|HU2-AC1|Se muestra el destinatario antes de confirmar.|Preparar un pago.|Pantalla.|

## 4.4 Criterios propios de la extensión “colecta escolar”

|ID|Criterio|Prueba|Evidencia|
|-|-|-|-|
|COL-01|Se ve la meta de la colecta.|Abrir el panel.|Meta visible.|
"""


FEATURE = {
    "title": "HU-14 - Crear cuenta",
    "description": "Registrar cuentas.",
    "acceptance_criteria": ["La API responde 201"],
    "issue_number": 14,
    "labels": ["historia"],
}


class MainModeTests(unittest.TestCase):
    def test_developer_receives_approved_architecture(self):
        task = app._development_task(
            "developer", FEATURE, Path("workspace"), "existing source", "PO spec", "prior decisions",
            {"architect": "Approved POST /accounts contract"},
        )
        self.assertIn("Approved POST /accounts contract", task.description)
        self.assertIn("existing source", task.description)

    def test_architecture_comment_requires_confirmation(self):
        with patch.object(app, "create_issue_comment") as create_comment, \
                patch("builtins.input", return_value="n"), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(app._publish_architecture_comment(FEATURE, "Architecture"))
        create_comment.assert_not_called()

        with patch.object(app, "create_issue_comment") as create_comment, \
                patch("builtins.input", return_value="s"), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(app._publish_architecture_comment(FEATURE, "Architecture"))
        create_comment.assert_called_once()
        self.assertIn("crewai-architecture:issue-14", create_comment.call_args.args[1])

    def test_architect_reads_comments_for_po_related_stories(self):
        related = {
            **FEATURE, "issue_number": 12, "title": "HU-12 - Identidad",
            "product_owner_spec_path": "product-owner/issue-12-hu-12-identidad/product_owner_spec.md",
        }
        current = {
            **FEATURE,
            "product_owner_spec_path": "product-owner/issue-14-hu-14-crear-cuenta/product_owner_spec.md",
        }
        decision = "<!-- crewai-architecture:issue-12 -->\nContrato aprobado: UUID."
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            for feature in (current, related):
                path = output / feature["product_owner_spec_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
            (output / current["product_owner_spec_path"]).write_text(
                "3. Dependencias con otras HUs\nBloqueante: HU-12 - Identidad (#12).\n4. Especificaciones",
                encoding="utf-8",
            )
            (output / related["product_owner_spec_path"]).write_text("Especificación HU-12", encoding="utf-8")
            with patch.object(app, "OUTPUT_DIR", output), \
                    patch.object(app, "list_issue_comments", return_value=[{"body": decision}]) as list_comments:
                po_context, previous_decisions, related_features = app._architecture_context(current, [current, related])
                (output / current["product_owner_spec_path"]).write_text(
                    "3. Dependencias con otras HUs\nSin dependencias conocidas.\n4. Especificaciones",
                    encoding="utf-8",
                )
                (output / related["product_owner_spec_path"]).write_text(
                    "3. Dependencias con otras HUs\nDependiente: HU-14 - Crear cuenta (#14).\n4. Especificaciones",
                    encoding="utf-8",
                )
                inverse_relations = app._related_features(current, [current, related])
        self.assertEqual(related_features, [related])
        self.assertIn("Especificación HU-12", po_context)
        self.assertIn("Contrato aprobado: UUID", previous_decisions)
        self.assertEqual(inverse_relations, [related])
        list_comments.assert_called_once_with(12)

    def test_mode_one_reads_the_plan_and_does_not_list_issues(self):
        project = {"id": "P1", "title": "backlog-hackaton-grupo-08"}
        with patch.object(app, "proj_tools"), \
                patch.object(app, "list_projects", return_value=[project]), \
                patch.object(app, "list_project_features") as list_features, \
                patch.object(app, "run_product_owner_from_plan") as run_plan, \
                patch("builtins.input", return_value="1"), contextlib.redirect_stdout(io.StringIO()):
            app.main()
        run_plan.assert_called_once_with(project)
        list_features.assert_not_called()
    def test_mode_two_lists_and_dispatches_selected_issue(self):
        features = [
            FEATURE,
            {**FEATURE, "issue_number": 15, "title": "HU-15 - Ajustar perfil", "state": "OPEN"},
            {**FEATURE, "issue_number": 16, "title": "HU-16 - Cerrada", "state": "CLOSED"},
        ]
        output = io.StringIO()
        with patch.object(app, "proj_tools"), \
                patch.object(app, "list_projects", return_value=[{"id": "P1", "title": "backlog-hackaton-grupo-08"}]), \
                patch.object(app, "list_project_features", return_value=features), \
                patch.object(app, "run_development_flow") as run_development, \
                patch("builtins.input", side_effect=["2", "2"]), contextlib.redirect_stdout(output):
            app.main()
        run_development.assert_called_once_with(features[1], features)
        self.assertNotIn("HU-16 - Cerrada", output.getvalue())

    def run_plan(self, tmp, answers=("s",), **mcp):
        """Ejecuta el flujo del plan con el MCP simulado; devuelve (mocks, salida)."""
        output = Path(tmp) / "output"
        plan = Path(tmp) / "plan.md"
        if not plan.exists():
            plan.write_text(PLAN, encoding="utf-8")
        issues = iter(range(101, 200))
        defaults = {
            "verify_target_repo": MagicMock(),
            "ensure_labels": MagicMock(return_value=["historia", "extension"]),
            "find_issue_by_marker": MagicMock(return_value=None),
            "create_issue": MagicMock(side_effect=lambda title, body, labels: {
                "id": f"I_{title[:5]}", "number": next(issues), "url": f"https://github.com/o/r/issues/{title[:5]}"}),
            "add_issue_to_project": MagicMock(),
            "update_issue": MagicMock(),
        }
        defaults.update(mcp)
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(app, "OUTPUT_DIR", output))
        stack.enter_context(patch.dict("os.environ", {"PO_PLAN_FILE": str(plan)}))
        stack.enter_context(patch.object(app, "run_step", side_effect=lambda agent, task: "Spec generada"))
        stack.enter_context(patch.object(app, "hitl_approve", return_value=("s", "")))
        for name, mock in defaults.items():
            stack.enter_context(patch.object(app, name, mock))
        stack.enter_context(patch("builtins.input", side_effect=list(answers)))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        with stack:
            app.run_product_owner_from_plan({"id": "PVT_1", "title": "backlog-hackaton-grupo-08"})
        return defaults, output

    def test_plan_flow_creates_labeled_issues_and_links_each_to_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            mocks, output = self.run_plan(tmp)
            created = [call.args for call in mocks["create_issue"].call_args_list]
            self.assertEqual([c[0] for c in created], [
                "HU-01 - Registro y activación", "HU-02 - Confirmación de pagos", "Extensión: colecta escolar"])
            self.assertEqual([c[2] for c in created], [["historia"], ["historia"], ["extension"]])
            self.assertIn("HU1-AC1", created[0][1])
            self.assertIn("Spec generada", created[0][1])
            mocks["ensure_labels"].assert_called_once()
            linked = [call.args for call in mocks["add_issue_to_project"].call_args_list]
            self.assertEqual([args[0] for args in linked], ["PVT_1"] * 3)
            self.assertEqual([args[1] for args in linked], ["I_HU-01", "I_HU-02", "I_Exten"])
            checkpoint = json.loads((output / ".product_owner_plan_checkpoint.json").read_text())
            self.assertTrue(all(r["project_linked"] and r["number"] for r in checkpoint["published"].values()))
            self.assertTrue(any(output.glob("product-owner/plan-hu-01-*/product_owner_spec.md")))
            self.assertTrue(any(output.glob("product-owner/issue-101-*/product_owner_spec.md")))

    def test_only_official_stories_when_the_extension_is_declined(self):
        with tempfile.TemporaryDirectory() as tmp:
            mocks, _ = self.run_plan(tmp, answers=("h",))
            self.assertEqual(mocks["create_issue"].call_count, 2)
            self.assertEqual(mocks["add_issue_to_project"].call_count, 2)

    def test_cancelling_publishes_nothing_but_keeps_the_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            mocks, output = self.run_plan(tmp, answers=("n",))
            for name in ("verify_target_repo", "ensure_labels", "create_issue", "add_issue_to_project"):
                mocks[name].assert_not_called()
            self.assertEqual(len(list(output.glob("product-owner/plan-*/product_owner_spec.md"))), 3)

    def test_rerun_does_not_duplicate_or_regenerate_and_retries_only_the_failed_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = MagicMock(side_effect=[None, RuntimeError("proyecto no disponible"), None])
            first, output = self.run_plan(tmp, add_issue_to_project=link)
            self.assertEqual(first["create_issue"].call_count, 3)
            checkpoint = json.loads((output / ".product_owner_plan_checkpoint.json").read_text())
            self.assertEqual([k for k, r in checkpoint["published"].items() if not r.get("project_linked")], ["HU-02"])
            # Segunda ejecución sobre el mismo OUTPUT_DIR: solo debe reintentar la asociación fallida.
            second_link = MagicMock()
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(app, "OUTPUT_DIR", output))
                stack.enter_context(patch.dict("os.environ", {"PO_PLAN_FILE": str(Path(tmp) / "plan.md")}))
                run_step = stack.enter_context(patch.object(app, "run_step"))
                create = stack.enter_context(patch.object(app, "create_issue"))
                for name, mock in (("verify_target_repo", MagicMock()), ("ensure_labels", MagicMock(return_value=[])),
                                   ("find_issue_by_marker", MagicMock(return_value=None)),
                                   ("add_issue_to_project", second_link)):
                    stack.enter_context(patch.object(app, name, mock))
                stack.enter_context(patch("builtins.input", return_value="s"))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                app.run_product_owner_from_plan({"id": "PVT_1", "title": "backlog"})
            run_step.assert_not_called()
            create.assert_not_called()
            second_link.assert_called_once_with("PVT_1", "I_HU-02")

    def test_an_existing_issue_is_edited_instead_of_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = {"id": "I_old", "number": 7, "url": "https://github.com/o/r/issues/7"}
            find = MagicMock(side_effect=lambda marker, story_id=None: existing if story_id == "HU-01" else None)
            mocks, _ = self.run_plan(tmp, find_issue_by_marker=find)
            self.assertEqual([c.args[0] for c in mocks["create_issue"].call_args_list][0], "HU-02 - Confirmación de pagos")
            update = mocks["update_issue"].call_args_list[0].args
            self.assertEqual(update[:2], (7, "HU-01 - Registro y activación"))
            self.assertIn("HU1-AC1", update[2])
            self.assertEqual(mocks["add_issue_to_project"].call_args_list[0].args, ("PVT_1", "I_old"))

    def test_wrong_target_repo_stops_before_creating_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            verify = MagicMock(side_effect=RuntimeError("El MCP apunta a otro repositorio"))
            mocks, _ = self.run_plan(tmp, verify_target_repo=verify)
            mocks["create_issue"].assert_not_called()
            mocks["add_issue_to_project"].assert_not_called()

    def test_missing_plan_file_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"PO_PLAN_FILE": str(Path(tmp) / "nope.md")}), \
                patch.object(app, "run_step") as run_step, patch.object(app, "create_issue") as create, \
                contextlib.redirect_stdout(io.StringIO()):
            app.run_product_owner_from_plan({"id": "P", "title": "t"})
        run_step.assert_not_called()
        create.assert_not_called()
    def test_development_approvals_do_not_create_pr_without_final_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            generated = {
                "architect": "Approved architecture",
                "developer": "Developer spec\n// path: src/main/java/AccountResource.java\n```java\nclass AccountResource {}\n```",
                "testing": "Test report\n// path: src/test/java/AccountResourceTest.java\n```java\nclass AccountResourceTest {}\n```",
                "security": "Security review",
            }
            agents = {
                "architect": app.architect.agent,
                "developer": app.developer.agent,
                "testing": app.testing.agent,
                "security": app.security.agent,
            }

            def run(agent, task):
                key = next(name for name, role_agent in agents.items() if agent is role_agent)
                return generated[key]

            with patch.object(app, "OUTPUT_DIR", output), \
                    patch.object(app.devops, "feature_repo", return_value="user/repo"), \
                    patch.object(app.devops, "feature_base_branch", return_value="main"), \
                    patch.object(app.devops, "prepare_workspace", return_value=workspace), \
                    patch.object(app.developer, "attach_workspace", return_value=SimpleNamespace(audit=[])) as attach, \
                    patch.object(app.devops, "workspace_changes", return_value=["src/main/java/AccountResource.java"]), \
                    patch.object(app.devops, "workspace_context", return_value="src/main/java/App.java"), \
                    patch.object(app, "_architecture_context", return_value=("PO context", "prior decision", [])), \
                    patch.object(app, "run_step", side_effect=run), \
                    patch.object(app, "hitl_approve", return_value=("s", "")), \
                    patch.object(app, "_publish_architecture_comment", return_value=True), \
                    patch.object(app, "_confirm_side_effect", return_value=False), \
                    patch.object(app.devops, "create_feature_pr") as create_pr, \
                    contextlib.redirect_stdout(io.StringIO()):
                app.run_development_flow(FEATURE, [FEATURE])

            attach.assert_called_once_with(workspace, app._ask_workspace_permission)
            create_pr.assert_not_called()
            self.assertTrue((workspace / "src/main/java/AccountResource.java").is_file())
            self.assertTrue((workspace / "src/test/java/AccountResourceTest.java").is_file())
            checkpoint = json.loads(next(output.rglob(".checkpoint.json")).read_text())
            self.assertEqual(
                [key for key, step in checkpoint["steps"].items() if step["status"] == "approved"],
                ["architect", "developer", "testing", "security"],
            )

    def test_development_creates_pr_only_after_explicit_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            outputs = iter([
                "Architecture",
                "Developer\n// path: src/App.java\n```java\nclass App {}\n```",
                "Testing\n// path: src/AppTest.java\n```java\nclass AppTest {}\n```",
                "Security",
            ])
            with patch.object(app, "OUTPUT_DIR", output), \
                    patch.object(app.devops, "feature_repo", return_value="user/repo"), \
                    patch.object(app.devops, "feature_base_branch", return_value="main"), \
                    patch.object(app.devops, "prepare_workspace", return_value=workspace), \
                    patch.object(app.developer, "attach_workspace", return_value=SimpleNamespace(audit=["creó src/App.java"])), \
                    patch.object(app.devops, "workspace_changes", return_value=["src/App.java", "src/AppTest.java"]), \
                    patch.object(app.devops, "workspace_context", return_value="inventory"), \
                    patch.object(app, "_architecture_context", return_value=("PO", "", [])), \
                    patch.object(app, "run_step", side_effect=lambda *_: next(outputs)) as run_step, \
                    patch.object(app, "hitl_approve", return_value=("s", "")), \
                    patch.object(app, "_publish_architecture_comment", return_value=True), \
                    patch.object(app, "_confirm_side_effect", return_value=True), \
                    patch.object(app.devops, "create_feature_pr", return_value="https://github.com/user/repo/pull/9") as create_pr, \
                    contextlib.redirect_stdout(io.StringIO()):
                app.run_development_flow(FEATURE, [FEATURE])
                app.run_development_flow(FEATURE, [FEATURE])
            create_pr.assert_called_once()
            self.assertEqual(run_step.call_count, 4)
            self.assertEqual(create_pr.call_args.args[-1], "main")
            checkpoint = json.loads(next(output.rglob(".checkpoint.json")).read_text())
            self.assertEqual(checkpoint["pull_request"], "https://github.com/user/repo/pull/9")


if __name__ == "__main__":
    unittest.main()