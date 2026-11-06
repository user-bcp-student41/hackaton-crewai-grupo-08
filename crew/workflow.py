"""Orden de ejecución y activación explícita del séptimo perfil."""
import os
from agents import architect, data, backend, frontend, testing, security, chapter

ROLES = (architect, backend, frontend, testing, security, chapter)
DATA_ROLES = (architect, data, backend, frontend, testing, security, chapter)


def include_data() -> bool:
    value = os.getenv("CREWAI_INCLUDE_DATA", "false").strip().lower()
    if value not in ("true", "false"):
        raise ValueError("CREWAI_INCLUDE_DATA debe ser true o false")
    return value == "true"


def workflow_steps(with_data=False):
    return tuple((role.KEY, role.LABEL, role.agent, role.SPEC_FILE, role.EXTRACT_CODE)
                 for role in (DATA_ROLES if with_data else ROLES))


STEPS = workflow_steps()


def build_tasks(feature: dict, with_data=False) -> dict:
    return {role.KEY: role.build_task(feature) for role in (DATA_ROLES if with_data else ROLES)}
