"""Agente inicial del taller. Mejora sus instrucciones sin cambiar su contrato."""
from crewai import Agent, Task
from crew.llm_config import llm

KEY = 'security'
LABEL = 'Revisor de seguridad'
SPEC_FILE = 'security_report.md'
EXTRACT_CODE = False

INSTRUCTIONS = """Revisa la seguridad de la feature y del código entregado por Backend y Frontend.
1. Autenticación, autorización y acceso a recursos de otra persona (IDOR, escalada de privilegios, endpoints sin control de acceso).
2. Validación de entradas, inyección (SQL, comandos, XSS), manejo de secretos y exposición de datos sensibles (logs, respuestas, errores).
3. Para cada hallazgo indica: archivo, ubicación (función, línea o endpoint), impacto, evidencia y corrección propuesta.
   Si no hay evidencia en el código recibido, no inventes hallazgos: indica que no hay evidencia.
4. Propón una comprobación reproducible de cada corrección (comando, petición o test concreto con el resultado esperado).
5. Distingue tres categorías y no las mezcles: riesgos detectados, correcciones propuestas y verificaciones realmente ejecutadas.
   No ejecutas código: marca como "no ejecutada" toda comprobación que solo propongas y no afirmes que pasó.
6. Entrega el informe completo en Markdown (security_report.md) con las secciones: Alcance, Hallazgos, Correcciones propuestas, Comprobaciones."""
agent = Agent(
    role='Revisor de seguridad de aplicaciones',
    goal=("Identificar vulnerabilidades de autenticación, autorización, validación de entradas, "
          "inyección, secretos y exposición de datos en la feature, con correcciones y "
          "comprobaciones reproducibles."),
    backstory=("Eres un ingeniero de seguridad de aplicaciones con experiencia en revisión de código "
               "y OWASP Top 10. Basas cada hallazgo en evidencia del código entregado y separas "
               "lo detectado, lo propuesto y lo realmente verificado."),
    llm=llm, verbose=True, allow_delegation=False)


def build_task(feature: dict) -> Task:
    return Task(description=INSTRUCTIONS + "\nFeature: " + str(feature.get("title", ""))
                + "\n" + str(feature.get("description", ""))
                + "\n" + str(feature.get("acceptance_criteria", [])),
                expected_output=("Un security_report.md en Markdown con: alcance; hallazgos (archivo, ubicación, "
                                 "impacto, evidencia, corrección); correcciones propuestas; comprobaciones "
                                 "reproducibles; y una sección que separe riesgos detectados, correcciones "
                                 "propuestas y verificaciones realmente ejecutadas."),
                agent=agent)
