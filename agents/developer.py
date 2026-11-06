"""Agente Full Stack: implementa la HU en el workspace clonado con herramientas de archivos."""
from typing import Callable

from crewai import Agent, Task
from crew.llm_config import get_agentic_llm
from crew.workspace_tools import WorkspaceAccess, build_tools

KEY = "developer"
LABEL = "Developer Full Stack"
SPEC_FILE = "developer_spec.md"
EXTRACT_CODE = True

INSTRUCTIONS = """Eres responsable de implementar la Historia de Usuario en el workspace del repositorio indicado.
El backend debe usar Quarkus con Java 21 y estilo imperativo; el frontend debe usar Angular.

HERRAMIENTAS (todas actúan solo sobre el workspace)
- list_files, read_file, search_text: explora antes de cambiar nada.
- write_file (crea o reemplaza un archivo completo), replace_in_file (edita un fragmento exacto), delete_path (elimina).
- run_command: ejecuta un programa sin shell (mvn, npm, java...). Cada comando lo aprueba una persona; úsalo solo para
  compilar o probar. git y gh no están disponibles: el flujo gestiona commit, push y PR.
- Si una herramienta responde que la persona denegó un permiso, no repitas esa acción: busca otra forma dentro del
  workspace o declara el cambio como pendiente. No intentes eludir un permiso por otra vía.

REGLAS DE IMPLEMENTACION
- Antes de editar, lee los archivos relacionados y sigue la arquitectura, convenciones, dependencias y contratos existentes.
- Implementa solamente los cambios necesarios para los criterios de aceptación y el diseño aprobado.
- Prefiere replace_in_file para cambios localizados; no reescribas archivos completos sin necesidad.
- No inventes clases, endpoints, tablas ni librerías existentes: compruébalo con las herramientas. Declara supuestos y pendientes.
- Incluye validación del lado servidor y manejo seguro de errores; no escribas secretos ni credenciales.
- Solo afirma que algo compila o que las pruebas pasan si lo ejecutaste con run_command y citas la salida literal;
  en otro caso marca la verificación como NO EJECUTADA.

ENTREGABLE
Tu respuesta final es developer_spec.md, sin pegar el contenido completo de los archivos (ya están en el workspace):
resumen, lista de archivos creados, modificados y eliminados, trazabilidad criterio -> cambio, comandos ejecutados con su
resultado, verificaciones recomendadas y pendientes (incluidos los permisos denegados).

Si falta información o el contrato arquitectónico contradice al código disponible, detalla el conflicto y no lo resuelvas en silencio."""

agent = Agent(
    role="Desarrollador Full Stack",
    goal=("Implementar una HU aprobada en un proyecto existente con Quarkus, Java 21 imperativo y Angular, "
          "respetando los contratos y convenciones descubiertos."),
    backstory=("Eres un desarrollador Full Stack senior. Trabajas sobre un workspace clonado y una rama de feature "
               "preparada para ti; editas archivos con tus herramientas, pides permiso cuando te falta uno y no "
               "publicas nada."),
    llm=get_agentic_llm(),
    verbose=True,
    allow_delegation=False,
)


def attach_workspace(workspace, ask: Callable[[str], str]) -> WorkspaceAccess:
    """Liga las herramientas al workspace; `ask` consulta a la persona (s una vez, a siempre, n denegar)."""
    access = WorkspaceAccess(workspace, ask)
    agent.llm.bind(build_tools(access), str(access.root))
    return access


def build_task(feature: dict, workspace_path: str = "", project_context: str = "",
               architecture_context: str = "", prior_decisions: str = "") -> Task:
    context = (
        f"\nWorkspace clonado: {workspace_path or '(no indicado)'}"
        f"\n\nInventario y contexto del repositorio:\n{project_context or '(sin contexto disponible)'}"
        f"\n\nContrato aprobado por Arquitectura:\n{architecture_context or '(pendiente)'}"
        f"\n\nDecisiones de arquitectura en Issues relacionados:\n{prior_decisions or '(no hay comentarios previos disponibles)'}"
    )
    description = (
        INSTRUCTIONS
        + "\n\nHistoria de Usuario: " + str(feature.get("title", ""))
        + "\nDescripción: " + str(feature.get("description", ""))
        + "\nCriterios de aceptación: " + str(feature.get("acceptance_criteria", []))
        + context
    )
    return Task(
        description=description,
        expected_output=("developer_spec.md con resumen, archivos creados/modificados/eliminados, trazabilidad de "
                         "criterios, comandos ejecutados y pendientes. El código ya está escrito en el workspace "
                         "con las herramientas; no lo repitas. Backend Quarkus Java 21 imperativo y frontend Angular."),
        agent=agent,
    )