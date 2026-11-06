"""Perfil inicial opcional para equipos de siete: datos y persistencia."""
from crewai import Agent, Task
from crew.llm_config import llm

KEY = 'data'
LABEL = 'Datos y persistencia'
SPEC_FILE = 'data_spec.md'
EXTRACT_CODE = True

INSTRUCTIONS = "Define tablas, relaciones, restricciones y migraciones a partir de la arquitectura aprobada."
agent = Agent(role=LABEL, goal="Diseñar la persistencia del requerimiento.",
              backstory="Eres el responsable de datos del equipo.", llm=llm,
              verbose=True, allow_delegation=False)


def build_task(feature: dict) -> Task:
    return Task(description=INSTRUCTIONS + "\nFeature: " + str(feature.get("title", ""))
                + "\n" + str(feature.get("description", ""))
                + "\n" + str(feature.get("acceptance_criteria", [])),
                expected_output='Tablas, relaciones, claves primarias y foráneas, restricciones, índices y migración que conserve los datos, con estrategia de reversión. '
                'SQL en bloques markdown con primera línea -- nombre.sql. No ejecutes migraciones ni inventes evidencia. '
                'Si no requiere persistencia, justifica la decisión sin generar SQL.', agent=agent)
