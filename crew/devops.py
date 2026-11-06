"""DevOps: publica en ai-labs el código aprobado como dos PR (backend -> api/, frontend -> web/).

No es un paso del LLM: ejecuta git y gh de forma determinista tras la aprobación humana final.
El veredicto del Chapter es informativo: se muestra y se cita en el PR, pero no bloquea.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from crew.workspace_tools import WORKSPACE_EXCLUDED, is_sensitive_name

# (clave, carpeta en output/, ruta destino en ai-labs, spec que alimenta el cuerpo del PR)
TARGETS = (
    ("backend", "backend-quarkus", "api", "backend_spec.md"),
    ("frontend", "frontend-angular", "web", "frontend_spec.md"),
)
EXCLUDED = ("target", "node_modules", ".angular", "dist", ".git", "__pycache__", ".env*")
VERDICT = re.compile(r"VEREDICTO:\s*\**\s*(APROBADO|RECHAZADO)", re.IGNORECASE)
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SPEC_EXTRACT = 4000
FEATURE_REPO_DEFAULT = "user-bcp-student41/hackaton-grupo-08"
FEATURE_BASE_DEFAULT = "main"
WORKSPACE_SOURCE_EXTENSIONS = {".java", ".ts", ".html", ".css", ".scss", ".json", ".xml", ".sql"}
WORKSPACE_CONTEXT_LIMIT = 20000
WORKSPACE_FILE_LIMIT = 40


def enabled() -> bool:
    value = os.getenv("CREWAI_PUBLISH_PRS", "false").strip().lower()
    if value not in ("true", "false"):
        raise ValueError("CREWAI_PUBLISH_PRS debe ser true o false")
    return value == "true"


def chapter_verdict(chapter_text: str) -> str:
    """Devuelve APROBADO, RECHAZADO o '' si el Chapter no emitió veredicto."""
    verdicts = VERDICT.findall(chapter_text or "")
    return verdicts[-1].upper() if verdicts else ""


def _run(cmd: list, cwd=None) -> str:
    result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")[:40] or "feature"


def feature_repo() -> str:
    repo = os.getenv("FEATURE_REPO", FEATURE_REPO_DEFAULT).strip()
    if not REPO.match(repo):
        raise ValueError("FEATURE_REPO debe tener el formato owner/repository")
    return repo


def feature_base_branch() -> str:
    branch = os.getenv("FEATURE_BASE_BRANCH", FEATURE_BASE_DEFAULT).strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or branch.startswith("-"):
        raise ValueError("FEATURE_BASE_BRANCH no es un nombre de rama válido")
    return branch


def feature_branch(feature: dict) -> str:
    number = feature.get("issue_number") or feature.get("number")
    prefix = f"{number}-" if number else ""
    return f"feature/{prefix}{_slug(feature.get('title', ''))}"


def prepare_workspace(feature: dict, workspace_root: Path, repo: str | None = None,
                      base_branch: str | None = None) -> Path:
    """Clona el repositorio y crea una rama local; no hace push ni modifica GitHub."""
    repo = repo or feature_repo()
    if not REPO.match(repo):
        raise ValueError("El repositorio debe tener el formato owner/repository")
    base_branch = base_branch or feature_base_branch()
    workspace_root = Path(workspace_root).resolve()
    workspace = workspace_root / feature_branch(feature).replace("/", "-")
    branch = feature_branch(feature)

    if (workspace / ".git").exists():
        current = _run(["git", "branch", "--show-current"], workspace)
        if current == branch:
            return workspace
        if current != base_branch:
            raise RuntimeError(f"El workspace ya existe en la rama inesperada '{current}'.")
        _run(["git", "switch", "-c", branch], workspace)
        return workspace

    workspace_root.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", repo, str(workspace)])
    _run(["git", "switch", base_branch], workspace)
    _run(["git", "switch", "-c", branch], workspace)
    return workspace


def workspace_context(workspace: Path) -> str:
    """Construye un inventario y fragmentos acotados, omitiendo config y secretos."""
    root = Path(workspace).resolve()
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in WORKSPACE_EXCLUDED for part in relative.parts):
            continue
        name = path.name.lower()
        if is_sensitive_name(name):
            continue
        if path.suffix.lower() not in WORKSPACE_SOURCE_EXTENSIONS:
            continue
        files.append(path)

    inventory = [f"- {path.relative_to(root).as_posix()}" for path in files]
    sections = ["Inventario de archivos:\n" + ("\n".join(inventory[:WORKSPACE_FILE_LIMIT]) or "(sin archivos fuente)")]
    remaining = WORKSPACE_CONTEXT_LIMIT
    snippets = []
    for path in files[:WORKSPACE_FILE_LIMIT]:
        if remaining <= 0:
            break
        try:
            content = path.read_text(encoding="utf-8")[:3000]
        except (OSError, UnicodeDecodeError):
            continue
        content = content[:remaining]
        snippets.append(f"### {path.relative_to(root).as_posix()}\n```\n{content}\n```")
        remaining -= len(content)
    if snippets:
        sections.append("Fragmentos de archivos existentes:\n" + "\n\n".join(snippets))
    return "\n\n".join(sections)


def workspace_changes(workspace: Path) -> list[str]:
    """Archivos creados, editados o eliminados en el workspace respecto de HEAD.

    Excluye carpetas de build y archivos con posibles credenciales: no deben llegar al PR.
    """
    workspace = Path(workspace)
    tracked = _run(["git", "diff", "--name-only", "-z", "HEAD"], workspace)
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"], workspace)
    changed = []
    for name in (tracked + "\0" + untracked).split("\0"):
        parts = Path(name).parts
        if not name or any(part.casefold() in WORKSPACE_EXCLUDED for part in parts) or is_sensitive_name(parts[-1]):
            continue
        changed.append(Path(name).as_posix())
    return sorted(set(changed))


def apply_workspace_changes(text: str, workspace: Path) -> list[str]:
    """Extrae bloques `// path: ...` al workspace sin permitir rutas fuera del clone."""
    root = Path(workspace).resolve()
    block_pattern = re.compile(
        r"(?m)^\s*//\s*path:\s*([^\r\n]+)\s*\r?\n```[^\r\n]*\r?\n(.*?)^```\s*$",
        re.DOTALL | re.MULTILINE,
    )
    saved = []
    for match in block_pattern.finditer(str(text or "")):
        relative_text = match.group(1).strip().replace("\\", "/")
        relative = Path(relative_text)
        if relative.is_absolute() or any(part in ("", ".", "..") or part.casefold() == ".git" for part in relative.parts):
            raise ValueError(f"Ruta de archivo no permitida: {relative_text}")
        lowered = relative.name.lower()
        if is_sensitive_name(lowered):
            raise ValueError(f"Archivo sensible no permitido: {relative_text}")
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(f"La ruta sale del workspace: {relative_text}")
        if any(part.casefold() == ".git" for part in destination.relative_to(root).parts):
            raise ValueError(f"No se permiten cambios en metadatos Git: {relative_text}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(match.group(2).rstrip() + "\n", encoding="utf-8")
        saved.append(relative.as_posix())
    return sorted(set(saved))


def create_feature_pr(workspace: Path, feature: dict, changed_files: list[str],
                      repo: str | None = None, base_branch: str | None = None) -> str:
    """Publica los archivos aprobados y crea un PR; debe llamarse solo tras aprobación humana."""
    repo = repo or feature_repo()
    if not REPO.match(repo):
        raise ValueError("El repositorio debe tener el formato owner/repository")
    base_branch = base_branch or feature_base_branch()
    workspace = Path(workspace).resolve()
    branch = _run(["git", "branch", "--show-current"], workspace)
    if branch != feature_branch(feature):
        raise RuntimeError(f"El workspace está en '{branch}', no en '{feature_branch(feature)}'.")
    files = sorted({Path(path).as_posix() for path in changed_files})
    if not files:
        raise ValueError("No hay archivos aprobados para publicar.")
    for path in files:
        relative = Path(path)
        if relative.is_absolute() or any(part in ("..", ".") or part.casefold() == ".git" for part in relative.parts):
            raise ValueError(f"Ruta aprobada no válida: {path}")
    staged = _run(["git", "diff", "--cached", "--name-only"], workspace)
    if staged:
        raise RuntimeError("El workspace tiene cambios staged ajenos al flujo; no se publicarán.")
    _run(["git", "add", "--", *files], workspace)
    if not _run(["git", "status", "--porcelain", "--", *files], workspace):
        raise RuntimeError("Los archivos aprobados no contienen cambios para publicar.")
    _run(["git", "commit", "-m", f"feat: {feature.get('title', 'feature')}"] , workspace)
    _run(["git", "push", "-u", "origin", branch], workspace)
    title = f"feat: {feature.get('title', 'Feature')}"
    body = (
        f"## Historia de Usuario\n\n#{feature.get('issue_number', '')} {feature.get('title', '')}\n\n"
        "Implementación generada y revisada por el flujo CrewAI. Arquitectura, desarrollo, testing y seguridad "
        "fueron aprobados por una persona antes de publicar esta rama.\n"
    )
    return _run([
        "gh", "pr", "create", "--repo", repo, "--base", base_branch, "--head", branch,
        "--title", title, "--body", body,
    ], workspace)


def _body(feature: dict, spec_file: str, output_dir: Path, dest: str, files: int, verdict: str) -> str:
    spec = output_dir / "specs" / spec_file
    extract = spec.read_text(encoding="utf-8")[:SPEC_EXTRACT] if spec.is_file() else "(sin especificación)"
    chapter = f"VEREDICTO del Chapter: {verdict}." if verdict else "El Chapter no emitió veredicto."
    return (
        f"## Cambio\n\nFeature: **{feature.get('title', '')}**. "
        f"Publica {files} archivos en `{dest}/` generados por el flujo CrewAI.\n\n"
        f"## Origen\n\nTodas las etapas fueron aprobadas por una persona, que confirmó esta publicación. {chapter}\n\n"
        "## Validación\n\nNo ejecutada por el flujo. Los comandos de `testing_report.md` quedan "
        "NO EJECUTADO hasta que una persona los corra y adjunte la salida.\n\n"
        f"## Extracto de {spec_file}\n\n{extract}\n"
    )


def _publish_target(repo, base, clone, output_dir, feature, target, stamp, verdict) -> str:
    key, source, dest, spec_file = target
    src = output_dir / source
    files = [p for p in src.rglob("*") if p.is_file()] if src.is_dir() else []
    if not files:
        print(f"  [DevOps] {source}/ no tiene archivos; se omite el PR de {dest}/.")
        return ""
    branch = f"crewai/{_slug(feature.get('title', ''))}-{dest}-{stamp}"
    title = f"{feature.get('title', 'Feature')} ({dest})"
    _run(["git", "switch", base], clone)
    _run(["git", "switch", "-c", branch], clone)
    shutil.copytree(src, clone / dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*EXCLUDED))
    _run(["git", "add", "--", dest], clone)
    if not _run(["git", "status", "--porcelain", "--", dest], clone):
        print(f"  [DevOps] Sin cambios en {dest}/; no se crea PR.")
        return ""
    _run(["git", "commit", "-m", f"feat({dest}): {feature.get('title', 'feature')} (CrewAI)"], clone)
    _run(["git", "push", "-u", "origin", branch], clone)
    return _run(
        ["gh", "pr", "create", "--repo", repo, "--base", base, "--head", branch, "--title", title,
         "--body", _body(feature, spec_file, output_dir, dest, len(files), verdict)],
        clone,
    )


def publish(output_dir, feature: dict, chapter_text: str, published: dict, confirm=None) -> dict:
    """Abre un PR por destino pendiente. Devuelve {clave: url} incluyendo los ya publicados."""
    confirm = confirm or input
    published = dict(published or {})
    output_dir = Path(output_dir)
    verdict = chapter_verdict(chapter_text)
    repo = os.getenv("AI_LABS_REPO", "").strip()
    if not REPO.match(repo):
        print("\n[DevOps] Define AI_LABS_REPO=<owner>/ai-labs en .env para publicar los PR.")
        return published
    pending = [t for t in TARGETS if t[0] not in published]
    if not pending:
        print("\n[DevOps] Los PR ya fueron publicados: " + ", ".join(published.values()))
        return published
    destinos = ", ".join(f"{t[1]}/ -> {t[2]}/" for t in pending)
    print(f"\n[DevOps] Veredicto del Chapter: {verdict or 'sin veredicto'} (informativo).")
    answer = confirm(f"[DevOps] ¿Aprobación final: abrir PR en {repo} ({destinos})? [s/n]: ").strip().lower()
    if answer != "s":
        print("[DevOps] Publicación cancelada. Vuelve a ejecutar para reintentarla.")
        return published
    try:
        base = _run(["gh", "repo", "view", repo, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"])
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "ai-labs"
            _run(["gh", "repo", "clone", repo, str(clone)])
            stamp = time.strftime("%Y%m%d%H%M")
            for target in pending:
                try:
                    url = _publish_target(repo, base, clone, output_dir, feature, target, stamp, verdict)
                except subprocess.CalledProcessError as error:
                    print(f"  [DevOps] Falló el PR de {target[2]}/: {str(error.stderr or error).strip()}")
                    continue
                if url:
                    published[target[0]] = url
                    print(f"  [DevOps] PR {target[2]}/: {url}")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[DevOps] No se pudo publicar: {getattr(error, 'stderr', None) or error}")
    return published
