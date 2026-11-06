"""Check the testing agent's contract and that its report survives the code extractor."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main as app
from agents import testing

FEATURE = {
    "title": "Crear tarea",
    "description": "Crear una tarea con título",
    "acceptance_criteria": ["Rechazar un título vacío", "Guardar un título de hasta 100 caracteres"],
}

REPORT = """# Informe de pruebas
| CA | ID | Tipo | Resultado esperado | Estado |
| --- | --- | --- | --- | --- |
| CA-1 | T-1 | negativo | 400 con error de título | NO EJECUTADO |

```bash
cd output/backend-quarkus
mvn test -Dtest=TaskApiTest
```

```java
// TaskApiTest.java
package pe.bcp.login;
public class TaskApiTest {}
```

```sql
-- verify_tasks.sql
SELECT COUNT(*) FROM tasks;
```
"""


class TestingAgentTests(unittest.TestCase):
    def test_contract_keys_are_unchanged(self):
        self.assertEqual(
            (testing.KEY, testing.SPEC_FILE, testing.EXTRACT_CODE),
            ("testing", "testing_report.md", True),
        )

    def test_task_carries_feature_and_every_criterion(self):
        task = testing.build_task(FEATURE).description
        self.assertIn(FEATURE["title"], task)
        self.assertIn(FEATURE["description"], task)
        for criterion in FEATURE["acceptance_criteria"]:
            self.assertIn(criterion, task)

    def test_workspace_task_uses_repository_paths_and_existing_build(self):
        task = testing.build_task(FEATURE, "output/workspaces/feature-14").description
        self.assertIn("output/workspaces/feature-14", task)
        self.assertIn("archivos de build y scripts del proyecto", task)
        self.assertIn("// path: ruta/relativa/al/repositorio.ext", task)

    def test_instructions_require_traceability_and_honesty(self):
        text = testing.INSTRUCTIONS
        for required in ("positivo", "negativo", "borde", "integración", "NO EJECUTADO",
                         "Limpieza", "Contrato de API", "Contrato de persistencia", "Correcciones propuestas"):
            self.assertIn(required, text)
        self.assertIn("Nunca inventes", text)

    def test_bash_commands_are_not_saved_as_code_but_tests_are(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            output = Path(tmp)
            stack.enter_context(patch.object(app, "OUTPUT_DIR", output))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            saved = app.extract_and_save_code(REPORT)
        self.assertEqual(
            sorted(saved),
            ["backend-quarkus/src/test/java/pe/bcp/login/TaskApiTest.java", "db/verify_tasks.sql"],
        )


if __name__ == "__main__":
    unittest.main()
