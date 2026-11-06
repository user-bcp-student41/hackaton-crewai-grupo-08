"""Parser del plan de trabajo y cuerpo de las Issues que se publican."""

import unittest
from pathlib import Path

from crew import plan_stories

REAL_PLAN = Path(__file__).resolve().parents[1] / "plan-inicial-epica-hus.md"

SAMPLE = """# Plan
# 1\\. Alcance
## 1.6 Límite del alcance
**A. Onboarding de la wallet — HU-01**

* Flujo guiado con el paso actual.
* Validación de datos obligatorios.

**B. Pago de bajo monto a contacto — HU-02**

* Mostrar destinatario e importe.

# 2\\. Roles

## 4.1 HU-01 — Registro y activación

|ID|Criterio de aceptación de HU-01|Cómo lo probaremos|Evidencia|
|-|-|-|-|
|HU1-AC1|Muestra el paso actual.|Avanzar.|Captura.|
|HU1-AC2|Bloquea datos \\| inválidos.|Omitir un campo.|Pantalla.|

**Contexto y supuestos a respetar en HU-01**

* KYC lo define Cumplimiento.
* No inventar requisitos.

## 4.2 HU-02 — Confirmación de pagos

|ID|Criterio de aceptación de HU-02|Cómo lo probaremos|Evidencia|
|-|-|-|-|
|HU2-AC1|Muestra el destinatario.|Preparar un pago.|Pantalla.|

## 4.3 Requisitos transversales

|ID|Requisito|Prueba|Evidencia|
|-|-|-|-|
|EP-HU1\\_2-01|Reducir fricción.|Recorrer el flujo.|Secuencia.|
|EP-HU2-02|Solo aplica a HU-02.|Probar.|Evidencia.|

## 4.4 Criterios propios de la extensión “colecta escolar”

|ID|Criterio|Prueba|Evidencia|
|-|-|-|-|
|COL-01|Se ve la meta.|Abrir el panel.|Meta.|
"""


def by_id(stories):
    return {story["id"]: story for story in stories}


class ParsePlanTests(unittest.TestCase):
    def test_extracts_stories_criteria_scope_context_and_extension(self):
        stories = by_id(plan_stories.parse_plan(SAMPLE)["stories"])
        self.assertEqual(list(stories), ["HU-01", "HU-02", "EXT-COL"])
        hu1 = stories["HU-01"]
        self.assertEqual(hu1["title"], "HU-01 - Registro y activación")
        self.assertEqual([c["id"] for c in hu1["criteria"]], ["HU1-AC1", "HU1-AC2"])
        self.assertEqual(hu1["criteria"][1]["text"], "Bloquea datos | inválidos.")
        self.assertEqual(hu1["criteria"][0]["test"], "Avanzar.")
        self.assertEqual(hu1["scope"], ["Flujo guiado con el paso actual.", "Validación de datos obligatorios."])
        self.assertEqual(hu1["context"], ["KYC lo define Cumplimiento.", "No inventar requisitos."])
        self.assertEqual(hu1["labels"], ["historia"])
        self.assertTrue(stories["EXT-COL"]["extension"])
        self.assertEqual(stories["EXT-COL"]["title"], "Extensión: colecta escolar")
        self.assertEqual(stories["EXT-COL"]["labels"], ["extension"])
        self.assertEqual([c["id"] for c in stories["EXT-COL"]["criteria"]], ["COL-01"])

    def test_cross_cutting_requirements_only_reach_the_stories_they_name(self):
        stories = by_id(plan_stories.parse_plan(SAMPLE)["stories"])
        self.assertEqual([c["id"] for c in stories["HU-01"]["cross_cutting"]], ["EP-HU1_2-01"])
        self.assertEqual([c["id"] for c in stories["HU-02"]["cross_cutting"]], ["EP-HU1_2-01", "EP-HU2-02"])
        self.assertEqual(stories["EXT-COL"]["cross_cutting"], [])

    def test_a_document_without_stories_yields_nothing(self):
        self.assertEqual(plan_stories.parse_plan("# Notas\nSin historias.")["stories"], [])

    @unittest.skipUnless(REAL_PLAN.is_file(), "plan real no disponible")
    def test_the_real_plan_yields_both_official_stories_and_the_extension(self):
        stories = by_id(plan_stories.parse_plan(REAL_PLAN.read_text(encoding="utf-8"))["stories"])
        self.assertEqual(list(stories), ["HU-01", "HU-02", "EXT-COL"])
        self.assertEqual(len(stories["HU-01"]["criteria"]), 17)
        self.assertEqual(len(stories["HU-02"]["criteria"]), 6)
        self.assertEqual(len(stories["EXT-COL"]["criteria"]), 3)
        self.assertEqual(len(stories["HU-01"]["cross_cutting"]), 5)


class IssueContentTests(unittest.TestCase):
    def setUp(self):
        self.story = by_id(plan_stories.parse_plan(SAMPLE)["stories"])["HU-01"]

    def test_feature_carries_scope_criteria_and_assumptions_for_the_po_agent(self):
        feature = plan_stories.story_to_feature(self.story)
        self.assertEqual(feature["acceptance_criteria"][0], "HU1-AC1: Muestra el paso actual.")
        self.assertIn("KYC lo define Cumplimiento.", feature["description"])
        self.assertIn("EP-HU1_2-01", feature["description"])
        self.assertEqual(feature["plan_id"], "HU-01")

    def test_issue_body_has_marker_checklist_and_spec(self):
        body = plan_stories.issue_body(self.story, "ESPECIFICACION", "plan.md")
        self.assertTrue(body.startswith(plan_stories.story_marker("HU-01")))
        self.assertIn("- [ ] **HU1-AC1** — Muestra el paso actual.", body)
        self.assertIn("  - Prueba: Avanzar.", body)
        self.assertIn("ESPECIFICACION", body)
        self.assertIn("`plan.md`", body)

    def test_oversized_spec_is_trimmed_below_the_github_limit(self):
        body = plan_stories.issue_body(self.story, "x" * 200_000, "plan.md")
        self.assertLess(len(body), 65_536)
        self.assertIn("recortada", body)
        self.assertIn("HU1-AC1", body)


if __name__ == "__main__":
    unittest.main()
