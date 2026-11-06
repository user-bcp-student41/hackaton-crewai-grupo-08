"""Product Owner técnico: convierte la HU en especificaciones listas para el Arquitecto."""
from crewai import Agent, Task
from crew.llm_config import llm

KEY = 'product_owner'
LABEL = 'Product Owner técnico'
SPEC_FILE = 'product_owner_spec.md'
EXTRACT_CODE = False

INSTRUCTIONS = """Actúa como un Product Owner Técnico Senior especializado en arquitectura de microservicios (Java Quarkus).
Analiza la Historia de Usuario (HU) indicada al final (título, descripción y criterios de aceptación) y entrega un documento de
especificaciones técnicas listo para que lo revise el Arquitecto de Software. No escribes código ni ejecutas nada.

## Documento: estrictamente estas 5 secciones, con estos títulos y en este orden
1. Desglose de Criterios de Aceptación
   - Un bloque por criterio, numerado CA-1, CA-2... en el orden recibido, en formato Dado / Cuando / Entonces.
   - Cada Entonces es observable: status HTTP, campos del cuerpo, dato guardado o mensaje visible. No uses "funciona correctamente".
   - Si la HU trae pocos o ningún criterio, deriva los que falten de la descripción y márcalos como DERIVADO. Añade el caso de error
     y el caso límite de cada comportamiento.
2. Impacto en Microservicios y Componentes
   - Tabla: componente | tipo (servicio, base de datos, contrato de API, frontend) | cambio | nuevo o existente.
   - Indica qué contratos de API y qué estructuras de datos se crean, modifican o se ven afectados.
3. Dependencias con otras HUs
   - Bloqueantes: qué debe existir antes. Dependientes: qué se habilita después.
   - Usa solo HUs mencionadas en la entrada. Si falta información, escribe SUPUESTO y describe la dependencia por su capacidad,
     sin inventar identificadores de HU.
    - Cuando se provea el backlog del batch, contrasta esta HU con todas las demás y referencia cada dependencia confirmada
       con el número/título de la HU y la ruta de su especificación generada. Si no encuentras una dependencia sustentada, indícalo.
4. Especificaciones Técnicas para el Arquitecto
   - Endpoints estimados (REST): método, ruta, descripción, request, response de éxito y de error con status.
   - Payloads de ejemplo, con tipos y obligatoriedad de cada campo.
   - Cambios en modelos de datos y entidades: entidad, atributos, tipos, claves, restricciones, relaciones.
   - Marca todo lo que es una estimación y lo que debe decidir el Arquitecto.
5. Riesgos y Consideraciones
   - Rendimiento, seguridad (autenticación, autorización, validación de entradas, datos sensibles) y posibles cuellos de botella.
   - Por cada riesgo: impacto, probabilidad (alta, media, baja) y mitigación propuesta.

## Honestidad
- No inventes requisitos, HUs, servicios ni cifras que no estén en la entrada ni en el contexto aprobado. Lo no confirmado va como
  SUPUESTO y se repite en una lista corta al final de la sección 5 con el título "Preguntas abiertas".
- Si la entrada es ambigua o contradictoria, señálalo en lugar de elegir en silencio.

## Formato
- Markdown con las tablas en barras verticales. No incluyas bloques de código con nombres de archivo; los payloads de ejemplo van
  en bloques ```json sin nombre de archivo.
- Si recibes feedback humano, aplícalo de forma explícita y conserva lo ya aprobado.
"""
agent = Agent(role='Product Owner técnico senior',
              goal="Convertir la HU en criterios Dado/Cuando/Entonces, impacto en componentes, dependencias, especificaciones "
                   "técnicas y riesgos que el Arquitecto pueda revisar sin pedir aclaraciones, sin inventar requisitos.",
              backstory="Eres un Product Owner técnico con experiencia en microservicios Java Quarkus. Traduces historias de usuario "
                        "a especificaciones verificables, marcas como SUPUESTO todo lo que no está confirmado y piensas en "
                        "dependencias, seguridad y rendimiento desde el inicio.",
              llm=llm, verbose=True, allow_delegation=False)


def _reference(item: dict) -> str:
    if item.get("issue_number"):
        return f"Issue #{item['issue_number']}"
    return f"HU del plan {item.get('plan_id', '?')} (aún sin Issue)"


def build_task(feature: dict, backlog_features: list[dict] | None = None, plan_context: str = "") -> Task:
    backlog = []
    for candidate in backlog_features or []:
        same_number = feature.get("issue_number") and candidate.get("issue_number") == feature.get("issue_number")
        same_id = feature.get("issue_id") and candidate.get("issue_id") == feature.get("issue_id")
        same_plan = feature.get("plan_id") and candidate.get("plan_id") == feature.get("plan_id")
        if same_number or same_id or same_plan:
            continue
        backlog.append(
            f"- {_reference(candidate)} — {candidate.get('title', '(sin título)')}\n"
            f"  Etiquetas: {candidate.get('labels', [])}\n"
            f"  Descripción: {candidate.get('description', '')}\n"
            f"  Criterios: {candidate.get('acceptance_criteria', [])}\n"
            f"  Especificación generada: {candidate.get('product_owner_spec_path', '(pendiente de generar)')}"
        )
    batch_context = ""
    if backlog_features is not None:
        batch_context = "\n\nTodas las HUs del batch para analizar dependencias:\n" + (
            "\n".join(backlog) if backlog else "(no hay otras HUs en el batch)"
        )
    plan = ""
    if plan_context:
        plan = ("\n\nPlan de trabajo (fuente de verdad del alcance; no amplíes lo que declara fuera de alcance ni "
                "resuelvas sus decisiones pendientes, regístralas como SUPUESTO o pregunta abierta):\n" + plan_context)
    return Task(description=INSTRUCTIONS + "\nFeature: " + str(feature.get("title", ""))
                + "\n" + _reference(feature)
                + "\n" + str(feature.get("description", ""))
                + "\n" + str(feature.get("acceptance_criteria", []))
                + "\nEspecificación de esta HU: " + str(feature.get("product_owner_spec_path", SPEC_FILE))
                + batch_context + plan,
                expected_output='Documento Markdown con exactamente 5 secciones: Desglose de Criterios de Aceptación (Dado/Cuando/Entonces), '
                'Impacto en Microservicios y Componentes, Dependencias con otras HUs, Especificaciones Técnicas para el Arquitecto y '
                'Riesgos y Consideraciones, con los supuestos marcados.', agent=agent)