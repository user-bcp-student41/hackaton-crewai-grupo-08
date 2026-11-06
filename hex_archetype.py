"""
hex_archetype.py — Arquetipo de Arquitectura Hexagonal para BCP AI Lab Day 04.

Proporciona:
  - HEX_PROMPT_PREFIX : bloque de texto para inyectar en prompts LLM
  - scaffold(dir, title): crea la estructura de carpetas hexagonal
  - validate_structural(dir): verifica que existan las capas con archivos reales
  - validate_semantic(dir):   verifica que domain/ y application/ no importen infrastructure/
  - validate(dir):            ejecuta ambas y retorna reporte combinado

Estructura esperada en el directorio de salida:
  domain/
    model/          ← Entidades de negocio puras
    port/
      input/        ← Puertos de entrada (interfaces de casos de uso)
      output/       ← Puertos de salida (interfaces hacia infra)
  application/
    service/        ← Implementación de casos de uso
  infrastructure/
    adapter/
      input/        ← Adaptadores REST / CLI / mensajería
      output/       ← Adaptadores DB / APIs externas
    config/         ← Configuración del framework
"""
import re
from pathlib import Path

# ── Capas requeridas ────────────────────────────────────────────────────────
HEX_LAYERS: list[str] = [
    "domain/model",
    "domain/port/input",
    "domain/port/output",
    "application/service",
    "infrastructure/adapter/input",
    "infrastructure/adapter/output",
    "infrastructure/config",
]

# ── Bloque para inyectar en prompts LLM ────────────────────────────────────
HEX_PROMPT_PREFIX = """
=== ARQUITECTURA HEXAGONAL (PORTS & ADAPTERS) ===
Genera el código siguiendo ESTRICTAMENTE arquitectura hexagonal.
Organiza los archivos en estas capas:

  domain/model/         → Entidades puras. NUNCA importa de infrastructure/.
  domain/port/input/    → Interfaces que invoca el exterior (casos de uso).
  domain/port/output/   → Interfaces hacia repos, APIs, MQ (implementadas por infra).
  application/service/  → Implementación de casos de uso. Solo depende de domain/port/.
  infrastructure/adapter/input/  → Controllers REST, CLI, listeners.
  infrastructure/adapter/output/ → Repos JPA, HTTP clients, MQ producers.
  infrastructure/config/         → Beans, properties, configuración.

REGLA DE ORO: las dependencias solo van hacia adentro.
  infrastructure → application → domain  (nunca al revés)
===================================================
"""


# ── Scaffold ────────────────────────────────────────────────────────────────
def scaffold(output_dir: Path | str, feature_title: str = "Feature") -> Path:
    """Crea la estructura de carpetas hexagonal. Retorna la raíz creada."""
    root = Path(output_dir)
    for layer in HEX_LAYERS:
        layer_path = root / layer
        layer_path.mkdir(parents=True, exist_ok=True)
        if not any(layer_path.iterdir()):
            (layer_path / ".gitkeep").touch()

    readme = root / "ARCHITECTURE.md"
    if not readme.exists():
        readme.write_text(
            f"# Arquitectura Hexagonal — {feature_title}\n\n"
            "```\n"
            "domain/\n"
            "  model/                ← Entidades puras\n"
            "  port/input/           ← Puertos de entrada\n"
            "  port/output/          ← Puertos de salida\n"
            "application/service/    ← Casos de uso\n"
            "infrastructure/\n"
            "  adapter/input/        ← Adaptadores REST/CLI\n"
            "  adapter/output/       ← Adaptadores DB/APIs\n"
            "  config/               ← Configuración\n"
            "```\n",
            encoding="utf-8",
        )
    print(f"[hex_archetype] Estructura creada en: {root}")
    return root


# ── Validación estructural ──────────────────────────────────────────────────
def validate_structural(output_dir: Path | str) -> dict[str, bool]:
    """Verifica que cada capa exista y tenga al menos un archivo real."""
    root = Path(output_dir)
    results: dict[str, bool] = {}
    for layer in HEX_LAYERS:
        lp = root / layer
        has_code = lp.exists() and any(
            f for f in lp.iterdir()
            if f.is_file() and f.name not in (".gitkeep", ".gitignore")
        )
        results[f"hex/{layer}"] = has_code
    return results


# ── Validación semántica ────────────────────────────────────────────────────
_INFRA_PATTERNS = [
    re.compile(r"from\s+infrastructure[.\s]",    re.MULTILINE),
    re.compile(r"import\s+infrastructure[.\s]",  re.MULTILINE),
    re.compile(r"import\s+[\w.]*\.infrastructure\b", re.MULTILINE),  # Java
]

def validate_semantic(output_dir: Path | str) -> dict:
    """Verifica la regla de inversión de dependencias en domain/ y application/."""
    root = Path(output_dir)
    violations: list[str] = []
    for restricted in ("domain", "application"):
        rdir = root / restricted
        if not rdir.exists():
            continue
        for f in rdir.rglob("*"):
            if not f.is_file() or f.suffix not in (".py", ".java", ".ts"):
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in _INFRA_PATTERNS:
                if pat.search(src):
                    rel = str(f.relative_to(root))
                    if rel not in violations:
                        violations.append(rel)
    return {
        "domain_sin_infra":      not any("domain"       in v for v in violations),
        "application_sin_infra": not any("application"  in v for v in violations),
        "violaciones":           violations,
    }


# ── Validación combinada ────────────────────────────────────────────────────
def validate(output_dir: Path | str) -> dict:
    """Ejecuta validación estructural + semántica y retorna reporte."""
    root     = Path(output_dir)
    struct   = validate_structural(root)
    sem      = validate_semantic(root)
    struct_ok = all(struct.values())
    sem_ok    = sem["domain_sin_infra"] and sem["application_sin_infra"]
    passed    = struct_ok and sem_ok

    lines = ["[hex_archetype] Validación de arquitectura hexagonal:"]
    lines.append("  ESTRUCTURAL:")
    for layer, ok in struct.items():
        lines.append(f"    {'OK' if ok else 'XX'} {layer}")
    lines.append("  SEMÁNTICA:")
    lines.append(f"    {'OK' if sem['domain_sin_infra'] else 'XX'} domain/ sin imports de infrastructure/")
    lines.append(f"    {'OK' if sem['application_sin_infra'] else 'XX'} application/ sin imports de infrastructure/")
    if sem["violaciones"]:
        lines.append(f"    !! Violaciones: {', '.join(sem['violaciones'])}")
    lines.append(f"  RESULTADO: {'APROBADO' if passed else 'RECHAZADO'}")
    summary = "\n".join(lines)
    print(summary)
    return {"structural": struct, "semantic": sem, "passed": passed, "summary": summary}
