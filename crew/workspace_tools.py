"""Herramientas de archivos y comandos del Developer, confinadas al workspace clonado.

Concedido por defecto: leer, buscar, crear, editar y borrar archivos dentro del workspace.
Todo lo demás se consulta a una persona antes de ejecutarse y, si se deniega, la herramienta
devuelve un error y el agente continúa sin ese cambio: rutas fuera del workspace, archivos con
credenciales, borrado recursivo de carpetas y cualquier comando.
"""
import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from copilot import ToolResult, define_tool
from pydantic import BaseModel, Field

WORKSPACE_EXCLUDED = {
    ".git", "node_modules", "target", "dist", "build", ".angular", "coverage",
    "__pycache__", ".venv", "venv",
}
SENSITIVE_PREFIXES = (".env", "secret", "credential")
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks")
SENSITIVE_NAMES = {"id_rsa", "id_ed25519", ".npmrc", ".pypirc"}
SHELLS = {"cmd", "powershell", "pwsh", "bash", "sh", "zsh", "wsl"}
PUBLISHERS = {"git", "gh"}
BATCH_METACHARACTERS = re.compile(r"[&|<>^%\r\n]")
SECRET_ENV_WORDS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY")

MAX_ENTRIES = 500
MAX_FILE_BYTES = 1_000_000
MAX_READ_CHARS = 60_000
MAX_WRITE_CHARS = 500_000
MAX_OUTPUT_CHARS = 8_000
MAX_TIMEOUT = 1_800

ALLOW_ONCE, ALLOW_ALWAYS = "s", "a"


def is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return (lowered.startswith(SENSITIVE_PREFIXES) or lowered.endswith(SENSITIVE_SUFFIXES)
            or lowered in SENSITIVE_NAMES)


class AccessError(Exception):
    """Acción no realizada; el mensaje se devuelve al agente."""

    def __init__(self, message: str, denied: bool = False):
        super().__init__(message)
        self.denied = denied


class WorkspaceAccess:
    """Política de permisos y operaciones sobre archivos. `ask` devuelve s (una vez), a (siempre) o n."""

    def __init__(self, root, ask: Callable[[str], str]):
        self.root = Path(root).resolve()
        self._ask = ask
        self._grants: set[str] = set()
        self.audit: list[str] = []

    def _authorize(self, key: str, question: str) -> None:
        if key in self._grants:
            return
        answer = (self._ask(question) or "n").strip().lower()
        if answer == ALLOW_ALWAYS:
            self._grants.add(key)
        elif answer != ALLOW_ONCE:
            self.audit.append(f"DENEGADO: {question}")
            raise AccessError(
                f"La persona denegó el permiso: {question} No repitas esta acción; usa otra alternativa "
                "dentro del workspace o declara el cambio como pendiente.", denied=True)
        self.audit.append(f"PERMITIDO: {question}")

    def _resolve(self, raw: str, action: str) -> Path:
        if not raw or "\x00" in raw:
            raise AccessError("La ruta está vacía o no es válida.")
        target = (self.root / raw).resolve()
        inside = target == self.root or target.is_relative_to(self.root)
        if inside and any(part.casefold() == ".git" for part in target.relative_to(self.root).parts):
            raise AccessError("No se permite acceder a .git: el flujo gestiona git.", denied=True)
        if not inside:
            self._authorize(f"outside:{action}:{target.parent}",
                            f"El Developer quiere {action} fuera del workspace: {target}.")
        elif is_sensitive_name(target.name):
            self._authorize(f"sensitive:{action}:{target}",
                            f"El Developer quiere {action} un archivo con posibles credenciales: {target}.")
        return target

    def _shown(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path)

    def _walk(self, base: Path, recursive: bool):
        for current, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d.casefold() not in WORKSPACE_EXCLUDED)
            for name in dirs:
                yield Path(current) / name, True
            for name in sorted(files):
                yield Path(current) / name, False
            if not recursive:
                break

    def list_files(self, path: str = ".", recursive: bool = False) -> str:
        base = self._resolve(path, "leer")
        if not base.is_dir():
            raise AccessError(f"No es un directorio: {path}")
        lines = []
        for entry, is_dir in self._walk(base, recursive):
            if len(lines) >= MAX_ENTRIES:
                lines.append(f"... (truncado a {MAX_ENTRIES} entradas; acota la ruta)")
                break
            lines.append(self._shown(entry) + ("/" if is_dir else ""))
        return "\n".join(lines) or "(directorio vacío)"

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        target = self._resolve(path, "leer")
        if not target.is_file():
            raise AccessError(f"No existe el archivo: {path}")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise AccessError(f"El archivo supera {MAX_FILE_BYTES} bytes; no se puede leer completo.")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        first = max(start_line or 1, 1)
        last = min(end_line or len(lines), len(lines))
        text = "\n".join(lines[first - 1:last])
        note = ""
        if len(text) > MAX_READ_CHARS:
            text, note = text[:MAX_READ_CHARS], "\n... (truncado; pide un rango de líneas)"
        return f"# {self._shown(target)} (líneas {first}-{last} de {len(lines)})\n{text}{note}"

    def search_text(self, query: str, path: str = ".", regex: bool = False, max_results: int = 100) -> str:
        if not query:
            raise AccessError("La búsqueda está vacía.")
        base = self._resolve(path, "leer")
        try:
            pattern = re.compile(query if regex else re.escape(query))
        except re.error as error:
            raise AccessError(f"Expresión regular inválida: {error}")
        hits = []
        files = [base] if base.is_file() else [e for e, is_dir in self._walk(base, True) if not is_dir]
        for file in files:
            if is_sensitive_name(file.name) or file.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                content = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{self._shown(file)}:{number}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        return "\n".join(hits) + "\n... (máximo de resultados alcanzado)"
        return "\n".join(hits) or "(sin coincidencias)"

    def write_file(self, path: str, content: str) -> str:
        if len(content) > MAX_WRITE_CHARS:
            raise AccessError(f"El contenido supera {MAX_WRITE_CHARS} caracteres; divídelo en archivos.")
        target = self._resolve(path, "escribir")
        if target.is_dir():
            raise AccessError(f"{path} es un directorio.")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        self.audit.append(f"{'modificó' if existed else 'creó'} {self._shown(target)}")
        return f"{'Reemplazado' if existed else 'Creado'}: {self._shown(target)} ({len(content)} caracteres)"

    def replace_in_file(self, path: str, old_text: str, new_text: str) -> str:
        if not old_text:
            raise AccessError("old_text no puede estar vacío; usa write_file para crear archivos.")
        target = self._resolve(path, "escribir")
        if not target.is_file():
            raise AccessError(f"No existe el archivo: {path}")
        with open(target, encoding="utf-8", newline="") as handle:
            content = handle.read()
        old, new = old_text, new_text
        if old not in content and "\r\n" in content:
            old, new = old_text.replace("\n", "\r\n"), new_text.replace("\n", "\r\n")
        count = content.count(old)
        if count != 1:
            raise AccessError(f"old_text aparece {count} veces en {path}; debe aparecer exactamente una. "
                              "Incluye más contexto y vuelve a intentarlo.")
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(content.replace(old, new, 1))
        self.audit.append(f"modificó {self._shown(target)}")
        return f"Editado: {self._shown(target)}"

    def delete_path(self, path: str, recursive: bool = False) -> str:
        target = self._resolve(path, "eliminar")
        if target == self.root:
            raise AccessError("No se puede eliminar la raíz del workspace.", denied=True)
        if not target.exists():
            raise AccessError(f"No existe: {path}")
        if target.is_dir():
            if not recursive:
                if any(target.iterdir()):
                    raise AccessError(f"{path} no está vacío; usa recursive=true (requiere aprobación).")
                target.rmdir()
            else:
                self._authorize(f"delete-dir:{target}",
                                f"El Developer quiere eliminar la carpeta y todo su contenido: {target}.")
                shutil.rmtree(target)
        else:
            target.unlink()
        self.audit.append(f"eliminó {self._shown(target)}")
        return f"Eliminado: {self._shown(target)}"

    def run_command(self, executable: str, args: list[str] | None = None, cwd: str = ".",
                    timeout_seconds: int = 300) -> str:
        args = [str(a) for a in (args or [])]
        program = Path(executable).stem.casefold()
        if program in PUBLISHERS:
            raise AccessError("git y gh no están disponibles: el flujo gestiona commits, push y PR.", denied=True)
        if program in SHELLS:
            raise AccessError("No se permiten shells; ejecuta el programa directamente (mvn, npm, java...).",
                              denied=True)
        resolved = shutil.which(executable)
        if not resolved:
            raise AccessError(f"No se encontró el programa: {executable}")
        if resolved.lower().endswith((".cmd", ".bat")) and any(BATCH_METACHARACTERS.search(a) for a in args):
            raise AccessError("Los argumentos contienen caracteres no permitidos para scripts .cmd/.bat.")
        workdir = self._resolve(cwd, "leer")
        if not workdir.is_dir():
            raise AccessError(f"cwd no es un directorio: {cwd}")
        command_line = " ".join([executable, *args])
        self._authorize(f"command:{program}", f"El Developer quiere ejecutar `{command_line}` en {workdir}.")
        env = {k: v for k, v in os.environ.items() if not any(w in k.upper() for w in SECRET_ENV_WORDS)}
        timeout = min(max(int(timeout_seconds), 1), MAX_TIMEOUT)
        try:
            done = subprocess.run([resolved, *args], cwd=workdir, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout,
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            self.audit.append(f"ejecutó (tiempo agotado): {command_line}")
            raise AccessError(f"El comando superó {timeout} s y fue detenido.")
        self.audit.append(f"ejecutó (código {done.returncode}): {command_line}")
        output = (done.stdout or "") + (done.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = "... (salida recortada)\n" + output[-MAX_OUTPUT_CHARS:]
        return f"Código de salida: {done.returncode}\n{output}".rstrip()


class ListFilesParams(BaseModel):
    path: str = Field(".", description="Carpeta relativa al workspace.")
    recursive: bool = Field(False, description="Incluir subcarpetas.")


class ReadFileParams(BaseModel):
    path: str = Field(description="Archivo relativo al workspace.")
    start_line: int | None = Field(None, description="Primera línea (1 = inicio).")
    end_line: int | None = Field(None, description="Última línea.")


class SearchTextParams(BaseModel):
    query: str = Field(description="Texto o expresión regular a buscar.")
    path: str = Field(".", description="Archivo o carpeta donde buscar.")
    regex: bool = Field(False, description="Interpretar query como expresión regular.")


class WriteFileParams(BaseModel):
    path: str = Field(description="Archivo relativo al workspace; se crea o reemplaza completo.")
    content: str = Field(description="Contenido completo del archivo.")


class ReplaceInFileParams(BaseModel):
    path: str = Field(description="Archivo existente relativo al workspace.")
    old_text: str = Field(description="Texto exacto a reemplazar; debe aparecer una sola vez.")
    new_text: str = Field(description="Texto nuevo.")


class DeletePathParams(BaseModel):
    path: str = Field(description="Archivo o carpeta relativa al workspace.")
    recursive: bool = Field(False, description="Eliminar una carpeta con su contenido (pide aprobación).")


class RunCommandParams(BaseModel):
    executable: str = Field(description="Programa a ejecutar, sin shell (por ejemplo mvn, npm, java).")
    args: list[str] = Field(default_factory=list, description="Argumentos, uno por elemento.")
    cwd: str = Field(".", description="Carpeta de trabajo relativa al workspace.")
    timeout_seconds: int = Field(300, description="Tiempo máximo en segundos.")


async def _call(func, *args):
    try:
        return await asyncio.to_thread(func, *args)
    except AccessError as error:
        return ToolResult(text_result_for_llm=str(error), error=str(error),
                          result_type="denied" if error.denied else "failure")


def build_tools(access: WorkspaceAccess) -> list:
    """Herramientas del SDK ligadas a `access`; el permiso se decide dentro de cada una."""

    @define_tool(name="list_files", skip_permission=True,
                 description="Lista archivos y carpetas del workspace (omite node_modules, target, .git).")
    async def list_files(params: ListFilesParams) -> str:
        return await _call(access.list_files, params.path, params.recursive)

    @define_tool(name="read_file", skip_permission=True,
                 description="Lee un archivo de texto del workspace, opcionalmente por rango de líneas.")
    async def read_file(params: ReadFileParams) -> str:
        return await _call(access.read_file, params.path, params.start_line, params.end_line)

    @define_tool(name="search_text", skip_permission=True,
                 description="Busca texto o regex en los archivos del workspace; devuelve archivo:línea.")
    async def search_text(params: SearchTextParams) -> str:
        return await _call(access.search_text, params.query, params.path, params.regex)

    @define_tool(name="write_file", skip_permission=True,
                 description="Crea o reemplaza un archivo completo dentro del workspace.")
    async def write_file(params: WriteFileParams) -> str:
        return await _call(access.write_file, params.path, params.content)

    @define_tool(name="replace_in_file", skip_permission=True,
                 description="Reemplaza un fragmento exacto (que aparezca una sola vez) en un archivo existente.")
    async def replace_in_file(params: ReplaceInFileParams) -> str:
        return await _call(access.replace_in_file, params.path, params.old_text, params.new_text)

    @define_tool(name="delete_path", skip_permission=True,
                 description="Elimina un archivo o una carpeta vacía; borrar una carpeta con contenido pide aprobación.")
    async def delete_path(params: DeletePathParams) -> str:
        return await _call(access.delete_path, params.path, params.recursive)

    @define_tool(name="run_command", skip_permission=True,
                 description="Ejecuta un programa (sin shell) en el workspace; cada comando pide aprobación humana.")
    async def run_command(params: RunCommandParams) -> str:
        return await _call(access.run_command, params.executable, params.args, params.cwd,
                           params.timeout_seconds)

    return [list_files, read_file, search_text, write_file, replace_in_file, delete_path, run_command]
