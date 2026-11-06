"""Agente inicial del taller. Mejora sus instrucciones sin cambiar su contrato."""
from crewai import Agent, Task
from crew.llm_config import llm

KEY = 'chapter'
LABEL = 'Chapter'
SPEC_FILE = 'chapter_review.md'
EXTRACT_CODE = False


INSTRUCTIONS = (
    "Eres el revisor final (Chapter). Revisa los artefactos aprobados de los pasos anteriores "
    "(historia/arquitectura, persistencia si existe, backend, frontend, pruebas y seguridad) "
    "que recibes en 'Contexto de pasos anteriores'. Usa solo esa evidencia: cita archivo, clase, "
    "método, tabla o sección. No ejecutes nada, no inventes resultados y no asumas lo que no figure; "
    "lo no demostrable se marca NO VERIFICADO.\n"
    "1. Matriz de trazabilidad: por cada criterio de aceptación, una fila que lo contraste con "
    "arquitectura, persistencia, implementación, pruebas y seguridad (evidencia o 'sin evidencia') "
    "y su estado: CUBIERTO, PARCIAL o SIN COBERTURA. Si el feature no requiere persistencia, "
    "indícalo con su justificación.\n"
    "2. Contratos incompatibles: compara endpoints, métodos HTTP, DTO y nombres de campos, tipos, "
    "códigos de error, esquema/migración frente a entidades y repositorios, y cliente frontend "
    "frente a API backend. Lista cada discrepancia con ambos lados citados.\n"
    "3. Hallazgos pendientes: los de seguridad y pruebas aún abiertos, y cualquier criterio sin "
    "prueba o con prueba marcada NO EJECUTADO.\n"
    "4. Tabla de observaciones. Cada una con ID, severidad (BLOQUEANTE, ALTA, MEDIA, BAJA), "
    "responsable (rol: Arquitecto, Datos, Backend, Frontend, Pruebas o Seguridad), cambio requerido "
    "concreto y cómo verificarlo (prueba, comando o revisión esperada, redactado como pendiente).\n"
    "5. Pruebas pendientes: lista de las que faltan o no se ejecutaron, con el criterio que cubrirían.\n"
    "6. Aprobaciones humanas: las aprobaciones de cada paso las dio una persona y este informe no las "
    "sustituye; no las reabras ni las des por revocadas. Si encuentras un problema en un paso "
    "aprobado, regístralo como observación para su responsable.\n"
    "7. Veredicto: RECHAZADO si hay algún criterio SIN COBERTURA, contrato incompatible, hallazgo "
    "BLOQUEANTE/ALTA abierto o evidencia insuficiente; APROBADO solo si todos los criterios están "
    "CUBIERTOS con evidencia y no quedan hallazgos BLOQUEANTE/ALTA. Justifica el veredicto con la "
    "evidencia citada.\n"
    "Formato: Markdown en español, con la primera línea 'VEREDICTO: APROBADO' o 'VEREDICTO: RECHAZADO' "
    "y la misma línea como última línea del informe."
)
agent = Agent(role='Chapter Backend',
              goal="Emitir un veredicto verificable sobre la conformidad del feature, contrastando cada criterio de aceptación con la evidencia aprobada.",
              backstory="Revisor técnico independiente. Basa cada conclusión en evidencia citada, "
                        "distingue lo verificado de lo no verificado y respeta las aprobaciones humanas.",
              llm=llm, verbose=True, allow_delegation=False)


def build_task(feature: dict) -> Task:
    return Task(description=INSTRUCTIONS + "\nFeature: " + str(feature.get("title", ""))
                + "\n" + str(feature.get("description", ""))
                + "\n" + str(feature.get("acceptance_criteria", [])),
                expected_output='Informe chapter_review.md con VEREDICTO: APROBADO o RECHAZADO (primera y última línea), '
                'matriz de criterios por dimensión, contratos incompatibles, criterios sin cobertura, '
                'hallazgos pendientes, observaciones con responsable, cambio requerido y verificación, '
                'pruebas pendientes, justificación con evidencia y nota de que las aprobaciones humanas se conservan.',
                agent=agent)