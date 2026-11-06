"""El Product Owner conserva el contrato de los agentes y pide las 5 secciones."""

import unittest

from agents import product_owner

FEATURE = {
    "title": "Crear proyecto base",
    "description": "Backend Quarkus y web.",
    "acceptance_criteria": ["El backend responde en /health", "La web consume el backend"],
}


class ProductOwnerTests(unittest.TestCase):
    def test_contract_keys(self):
        self.assertEqual(
            (product_owner.KEY, product_owner.SPEC_FILE, product_owner.EXTRACT_CODE),
            ("product_owner", "product_owner_spec.md", False),
        )

    def test_task_carries_feature_and_every_criterion(self):
        task = product_owner.build_task(FEATURE)
        self.assertIs(task.agent, product_owner.agent)
        for text in (FEATURE["title"], FEATURE["description"], *FEATURE["acceptance_criteria"]):
            self.assertIn(text, task.description)

    def test_batch_task_includes_other_stories_and_their_spec_paths(self):
        current = {
            **FEATURE, "issue_number": 14,
            "product_owner_spec_path": "product-owner/14-crear-cuenta/product_owner_spec.md",
        }
        other = {
            "title": "HU-12 - Identidad", "description": "Identificador común.",
            "acceptance_criteria": ["Conservar el formato"], "issue_number": 12,
            "labels": ["historia"],
            "product_owner_spec_path": "product-owner/12-identidad/product_owner_spec.md",
        }
        task = product_owner.build_task(current, [current, other])
        for expected in (
            "#12", other["title"], other["description"], other["product_owner_spec_path"],
            current["product_owner_spec_path"], "ruta de su especificación generada",
        ):
            self.assertIn(expected, task.description)

    def test_instructions_require_the_five_sections(self):
        for title in (
            "Desglose de Criterios de Aceptación",
            "Impacto en Microservicios y Componentes",
            "Dependencias con otras HUs",
            "Especificaciones Técnicas para el Arquitecto",
            "Riesgos y Consideraciones",
        ):
            self.assertIn(title, product_owner.INSTRUCTIONS)
        self.assertIn("Dado / Cuando / Entonces", product_owner.INSTRUCTIONS)
        self.assertIn("SUPUESTO", product_owner.INSTRUCTIONS)


    def test_plan_stories_are_referenced_by_plan_id_and_carry_the_plan_context(self):
        current = {**FEATURE, "plan_id": "HU-01", "title": "HU-01 - Registro"}
        other = {**FEATURE, "plan_id": "HU-02", "title": "HU-02 - Pagos",
                 "product_owner_spec_path": "product-owner/plan-hu-02-pagos/product_owner_spec.md"}
        task = product_owner.build_task(current, [current, other], "Fuera del alcance: despliegue multipaís.")
        for expected in ("HU del plan HU-02 (aún sin Issue)", other["product_owner_spec_path"],
                         "Fuera del alcance: despliegue multipaís.", "fuente de verdad del alcance"):
            self.assertIn(expected, task.description)
        self.assertEqual(task.description.count("HU-02 - Pagos"), 1)
        self.assertNotIn("Plan de trabajo", product_owner.build_task(current, [current]).description)

if __name__ == "__main__":
    unittest.main()
