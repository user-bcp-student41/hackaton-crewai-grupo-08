"""Configuración del proveedor LLM de S1."""

import os
from dotenv import load_dotenv
from crew.copilot_llm import AgenticCopilotLLM, CopilotLLM

load_dotenv()
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")


def get_llm() -> CopilotLLM:
    """Return the only supported provider for the lab."""
    return CopilotLLM(model=os.getenv("COPILOT_MODEL", "gpt-6-luna"))


def get_agentic_llm() -> AgenticCopilotLLM:
    """LLM del Developer: puede usar las herramientas de workspace que se le ligan."""
    return AgenticCopilotLLM(model=os.getenv("COPILOT_MODEL", "gpt-6-luna"))


llm = get_llm()
