"""CrewAI adapter for the GitHub Copilot Python SDK.

The SDK talks to the Copilot CLI runtime and uses the credentials from
the CLI's ``/login`` (or ``GH_TOKEN``/``COPILOT_GITHUB_TOKEN``). The adapter keeps
tool execution disabled because S1 already controls files and approvals.
"""

from __future__ import annotations

import asyncio
from typing import Any

from crewai.llms.base_llm import BaseLLM

from lab_copilot.runtime import complete as _complete, prompt_text as _prompt_text


class CopilotLLM(BaseLLM):
    """Synchronous CrewAI wrapper around the async Copilot SDK."""

    llm_type: str = "copilot"
    timeout: float = 600.0

    def call(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        if tools or available_functions:
            raise ValueError("CopilotLLM no ejecuta herramientas en S1.")
        if response_model is not None:
            raise ValueError(
                "CopilotLLM en S1 devuelve texto, no modelos estructurados."
            )
        return asyncio.run(_complete(_prompt_text(messages), self.model, self.timeout))

    async def acall(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        if tools or available_functions or response_model is not None:
            raise ValueError("CopilotLLM en S1 solo admite generación de texto.")
        return await _complete(_prompt_text(messages), self.model, self.timeout)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False


AGENTIC_SYSTEM_MESSAGE = (
    "Sigue las instrucciones del historial proporcionado por el laboratorio. Dispones solo de las herramientas "
    "de archivos y comandos registradas: úsalas para implementar el cambio en el workspace. Si una herramienta "
    "indica que la persona denegó un permiso, no repitas esa acción: usa otra alternativa o declara el cambio "
    "como pendiente. Al terminar, entrega solo el documento final solicitado.")


class AgenticCopilotLLM(CopilotLLM):
    """CopilotLLM que, con herramientas ligadas, deja actuar al modelo sobre un workspace.

    Las herramientas las ejecuta el SDK de Copilot; CrewAI sigue sin recibir herramientas.
    """

    session_tools: list[Any] = []
    session_directory: str | None = None
    session_timeout: float = 1800.0

    def bind(self, tools: list[Any], directory: str) -> None:
        self.session_tools = list(tools)
        self.session_directory = directory

    def call(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        if not self.session_tools:
            return super().call(messages, tools, callbacks, available_functions, from_task, from_agent,
                                response_model)
        if tools or available_functions or response_model is not None:
            raise ValueError("Las herramientas del Developer se registran con bind(), no vía CrewAI.")
        return asyncio.run(_complete(
            _prompt_text(messages), self.model, self.session_timeout, tools=self.session_tools,
            working_directory=self.session_directory, system_message=AGENTIC_SYSTEM_MESSAGE))
