"""Lee el plan de trabajo (markdown) y extrae historias, criterios y contexto para el flujo del PO."""
import re

STORY_HEADING = re.compile(r"^(#{1,6})\s+(?:\d+(?:\\?\.\d+)*\s+)?(HU-\d+)\s*[—–-]\s*(.+?)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
CRITERION_ID = re.compile(r"^[A-Z]+\d*-(?:AC|P)\d+$")
EXTENSION_ID = re.compile(r"^([A-Z]{2,6})-(\d+)$")
CROSS_CUTTING_ID = re.compile(r"^EP-HU([\d_]+)-(\d+)$")
CONTEXT_HEADER = re.compile(r"^\*\*Contexto y supuestos a respetar en (HU-\d+)\*\*\s*$")
SCOPE_HEADER = re.compile(r"^\*\*[A-Z]\.\s+.+?\s+[—–-]\s+(HU-\d+)\*\*\s*$")
FLOW_STEP = re.compile(r"^\d+\.\s+(.+?)\s*\((HU-\d+)\)\.?\s*$")
BULLET = re.compile(r"^[*-]\s+(.+?)\s*$")
UNESCAPE = re.compile(r"\\([_*\-\[\]#.!()+|])")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
QUOTED = re.compile(r"[“\"](.+?)[”\"]")
PLAN_CONTEXT_LIMIT = 9000
BODY_LIMIT = 60000


def _clean(text: str) -> str:
    return UNESCAPE.sub(r"\1", text).strip()


def _row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    cells = [_clean(cell) for cell in CELL_SPLIT.split(stripped)[1:-1]]
    return None if not cells or all(set(cell) <= set("-: ") for cell in cells) else cells


def _blocks(lines: list[str]) -> list[tuple[int, int, str, list[str]]]:
    """(nivel, línea, título, líneas del bloque) por encabezado, hasta el siguiente de igual o mayor rango."""
    headings = [(i, len(m.group(1)), m.group(2)) for i, line in enumerate(lines) if (m := HEADING.match(line))]
    blocks = []
    for position, (index, level, title) in enumerate(headings):
        end = len(lines)
        for next_index, next_level, _ in headings[position + 1:]:
            if next_level <= level:
                end = next_index
                break
        blocks.append((level, index, title, lines[index + 1:end]))
    return blocks


def _bullets_after(lines: list[str], start: int, stop) -> list[str]:
    found = []
    for line in lines[start:]:
        if not line.strip():
            continue
        if stop(line):
            break
        if match := BULLET.match(line.strip()):
            found.append(_clean(match.group(1)))
        else:
            break
    return found


def _criteria(block: list[str]) -> list[dict]:
    found = []
    for line in block:
        cells = _row(line)
        if cells and CRITERION_ID.match(cells[0]) and len(cells) >= 2:
            found.append({"id": cells[0], "text": cells[1], "test": cells[2] if len(cells) > 2 else "",
                          "evidence": cells[3] if len(cells) > 3 else ""})
    return found


def _new_story(story_id: str, name: str, extension: bool) -> dict:
    return {"id": story_id, "name": name, "title": name if extension else f"{story_id} - {name}",
            "extension": extension,
            "labels": ["extension"] if extension else ["historia"], "criteria": [], "scope": [], "flow": [],
            "context": [], "cross_cutting": []}


def parse_plan(text: str) -> dict:
    """Devuelve {"stories": [...], "context": str}; vacío si el documento no sigue el formato del plan."""
    lines = text.splitlines()
    stories: dict[str, dict] = {}
    for level, index, title, block in _blocks(lines):
        if match := STORY_HEADING.match(lines[index]):
            story_id, name = match.group(2), _clean(match.group(3))
            story = stories.setdefault(story_id, _new_story(story_id, name, False))
            story["criteria"] += _criteria(block)
            for offset, line in enumerate(block):
                if match := CONTEXT_HEADER.match(line.strip()):
                    story["context"] += _bullets_after(block, offset + 1, lambda l: l.startswith("#"))
            continue

    heading = ""
    extensions: dict[str, dict] = {}
    for line in lines:
        if match := HEADING.match(line):
            heading = match.group(2)
            continue
        cells = _row(line)
        if cells and len(cells) >= 2 and (match := EXTENSION_ID.match(cells[0])) and match.group(1) not in ("HU", "EP"):
            entry = extensions.setdefault(match.group(1), {"title": heading, "rows": []})
            entry["rows"].append({"id": cells[0], "text": cells[1], "test": cells[2] if len(cells) > 2 else "",
                                  "evidence": cells[3] if len(cells) > 3 else ""})
    for prefix, entry in extensions.items():
        quoted = QUOTED.search(entry["title"])
        name = _clean(quoted.group(1) if quoted else entry["title"])
        story = _new_story(f"EXT-{prefix}", f"Extensión: {name}", True)
        story["criteria"] = entry["rows"]
        stories[story["id"]] = story

    for line in lines:
        cells = _row(line)
        if cells and (m := CROSS_CUTTING_ID.match(cells[0])) and len(cells) >= 2:
            numbers = {int(n) for n in m.group(1).split("_")}
            item = {"id": cells[0], "text": cells[1], "test": cells[2] if len(cells) > 2 else "",
                    "evidence": cells[3] if len(cells) > 3 else ""}
            for story in stories.values():
                if not story["extension"] and int(re.search(r"\d+", story["id"]).group()) in numbers:
                    story["cross_cutting"].append(item)

    for index, line in enumerate(lines):
        if header := SCOPE_HEADER.match(_clean(line.strip())):
            if header.group(1) in stories:
                stories[header.group(1)]["scope"] += _bullets_after(
                    lines, index + 1, lambda l: l.startswith("**") or l.startswith("#"))
        if (step := FLOW_STEP.match(line.strip())) and step.group(2) in stories:
            stories[step.group(2)]["flow"].append(_clean(step.group(1)))

    start = next((i for i, l in enumerate(lines) if re.match(r"^#\s+1\\?\.", l)), None)
    end = next((i for i, l in enumerate(lines) if re.match(r"^#\s+2\\?\.", l)), None)
    context = "\n".join(lines[start:end]) if start is not None and end else text
    ordered = sorted(stories.values(), key=lambda s: (s["extension"], s["id"]))
    return {"stories": [s for s in ordered if s["criteria"]], "context": _clean(context)[:PLAN_CONTEXT_LIMIT]}


def story_to_feature(story: dict) -> dict:
    """Entrada del agente PO: el plan es la fuente de verdad de alcance, criterios y supuestos."""
    parts = []
    if story["scope"]:
        parts.append("Alcance incluido en el plan:\n" + "\n".join(f"- {s}" for s in story["scope"]))
    if story["flow"]:
        parts.append("Pasos del flujo principal:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(story["flow"], 1)))
    if story["context"]:
        parts.append("Contexto y supuestos a respetar:\n" + "\n".join(f"- {s}" for s in story["context"]))
    if story["cross_cutting"]:
        parts.append("Requisitos transversales de la épica aplicables:\n" + "\n".join(
            f"- {c['id']}: {c['text']} (Prueba: {c['test']})" for c in story["cross_cutting"]))
    return {
        "title": story["title"],
        "description": "\n\n".join(parts) or story["name"],
        "acceptance_criteria": [f"{c['id']}: {c['text']}" for c in story["criteria"]],
        "labels": list(story["labels"]),
        "plan_id": story["id"],
        "plan_story": story,
    }


def story_marker(story_id: str) -> str:
    return f"<!-- crewai-plan-story:{story_id} -->"


def issue_body(story: dict, spec: str, source: str) -> str:
    """Cuerpo de la Issue: definición de la HU con criterios como checklist y la spec del PO."""
    sections = [story_marker(story["id"]), f"## Historia\n\n{story['name']}"]
    if story["scope"]:
        sections.append("## Alcance\n\n" + "\n".join(f"- {s}" for s in story["scope"]))
    if story["flow"]:
        sections.append("## Flujo principal\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(story["flow"], 1)))
    criteria = []
    for c in story["criteria"]:
        criteria.append(f"- [ ] **{c['id']}** — {c['text']}")
        if c["test"]:
            criteria.append(f"  - Prueba: {c['test']}")
        if c["evidence"]:
            criteria.append(f"  - Evidencia: {c['evidence']}")
    sections.append("## Criterios de aceptación\n\n" + "\n".join(criteria))
    if story["cross_cutting"]:
        sections.append("## Requisitos transversales de la épica\n\n" + "\n".join(
            f"- **{c['id']}** — {c['text']}" for c in story["cross_cutting"]))
    if story["context"]:
        sections.append("## Contexto y supuestos\n\n" + "\n".join(f"- {s}" for s in story["context"]))
    footer = f"---\nOrigen: `{source}`. Generado por el flujo CrewAI del Product Owner."
    head = "\n\n".join(sections)
    room = BODY_LIMIT - len(head) - len(footer) - 200
    detail = spec.strip()
    if len(detail) > room:
        detail = detail[:max(room, 0)] + "\n\n... (recortada por el límite de GitHub; ver el archivo local)"
    return (f"{head}\n\n<details>\n<summary>Especificación técnica del Product Owner</summary>\n\n"
            f"{detail}\n\n</details>\n\n{footer}\n")
