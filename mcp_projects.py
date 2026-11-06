"""
Cliente HTTP para el MCP de proyectos — mcp-project :8080
Lee issues y features desde GitHub Projects via MCP Streamable HTTP.

Variables de entorno:
    PROJECTS_MCP_URL / MCP_PROJECT_URL   URL base (default: http://localhost:8080)
    MCP_TIMEOUT                          Timeout en segundos (default: 30)
    GITHUB_OWNER                         Owner de GitHub (org o usuario)
    GITHUB_REPO                          Repo por defecto
"""
import os
import re
import json
import threading
import requests

_URL     = os.getenv("PROJECTS_MCP_URL",     "http://localhost:8081")
_KEY     = os.getenv("PROJECTS_MCP_API_KEY", "")

_rpc_id       = 0
_id_lock      = threading.Lock()
_session_id   = None
_initialized  = False
_init_lock    = threading.Lock()


def _next_id() -> int:
    global _rpc_id
    with _id_lock:
        _rpc_id += 1
        return _rpc_id


def _headers() -> dict:
    hdrs = {
        "Authorization": f"Bearer {_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json, text/event-stream",
    }
    if _session_id:
        hdrs["Mcp-Session-Id"] = _session_id
    return hdrs


def _parse_sse_body(resp, msg_id) -> dict:
    """Lee un stream SSE de la respuesta del POST y retorna el JSON-RPC que
    coincide con msg_id (o el primero, si msg_id es None — notificaciones)."""
    data_buf = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw.startswith("data:"):
            data_buf.append(raw[5:].strip())
        elif raw == "":
            if not data_buf:
                continue
            payload_str = "\n".join(data_buf)
            data_buf     = []
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and (msg_id is None or payload.get("id") == msg_id):
                return payload
    raise RuntimeError("[MCP Proyectos] Stream SSE cerrado sin respuesta")


def _post_mcp(payload: dict, timeout: int) -> tuple[dict, str | None]:
    resp = requests.post(
        f"{_URL}/mcp",
        headers=_headers(),
        json=payload,
        stream=True,
        timeout=timeout,
    )
    resp.raise_for_status()
    sid   = resp.headers.get("Mcp-Session-Id")
    ctype = resp.headers.get("Content-Type", "")

    if "text/event-stream" in ctype:
        result = _parse_sse_body(resp, payload.get("id"))
    elif resp.content:
        result = resp.json()
    else:
        result = {}
    return result, sid


def _ensure_session(timeout: int = 20) -> None:
    """Handshake MCP: initialize → notifications/initialized (una sola vez)."""
    global _session_id, _initialized
    with _init_lock:
        if _initialized:
            return

        init_payload = {
            "jsonrpc": "2.0",
            "id":      _next_id(),
            "method":  "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities":    {},
                "clientInfo":      {"name": "s1-crewai", "version": "1.0.0"},
            },
        }
        result, sid = _post_mcp(init_payload, timeout)
        if "error" in result:
            raise RuntimeError(f"[MCP Proyectos] Error en initialize: {result['error']}")
        if sid:
            _session_id = sid

        try:
            _post_mcp(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                timeout,
            )
        except Exception:
            pass

        _initialized = True


def _sse_call(method: str, params: dict, timeout: int = 20) -> dict:
    """Envía un JSON-RPC 2.0 vía Streamable HTTP y retorna el resultado."""
    _ensure_session(timeout)

    msg_id  = _next_id()
    payload = {
        "jsonrpc": "2.0",
        "id":      msg_id,
        "method":  method,
        "params":  params,
    }

    try:
        result, sid = _post_mcp(payload, timeout)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"[MCP Proyectos] Error de conexión: {exc}") from exc

    if sid:
        global _session_id
        _session_id = sid

    if "error" in result:
        raise RuntimeError(f"[MCP Proyectos] Error RPC: {result['error']}")
    return result.get("result", {})


# ── API pública ────────────────────────────────────────────────────────────────

def list_tools() -> list[dict]:
    """Descubre las herramientas disponibles en el MCP de proyectos.

    Llama a tools/list vía Streamable HTTP y retorna la lista de herramientas:
        [{"name": "get_issue", "description": "...", "inputSchema": {...}}, ...]
    """
    result = _sse_call("tools/list", {})
    return result.get("tools", [])


def call_tool(tool: str, params: dict) -> dict:
    """Llama una herramienta del MCP de proyectos por nombre.

    Usa tools/call vía Streamable HTTP. El agente debe llamar list_tools()
    primero para conocer qué herramientas están disponibles.

    Importante: el protocolo MCP reporta los errores de ejecución de una tool
    como {"content": [...], "isError": true} DENTRO de un resultado JSON-RPC
    exitoso — no como el campo "error" de JSON-RPC. Si no se revisa "isError"
    aquí, un fallo de la tool (p.ej. parámetros inválidos) se interpreta
    silenciosamente como una respuesta vacía/válida.
    """
    result = _sse_call("tools/call", {"name": tool, "arguments": params})
    content = result.get("content", [])
    text = content[0]["text"] if content and content[0].get("type") == "text" else None

    if result.get("isError"):
        raise RuntimeError(f"[MCP Proyectos] Tool '{tool}' falló: {text or result}")

    if text is not None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
    return result


def discover_tool_schema(group: str, action: str | None = None) -> dict:
    """Introspecciona en runtime el esquema real de una tool vía discover_tools.

    Evita adivinar nombres de parámetros que pueden diferir entre versiones
    del server MCP (p.ej. `filterQuery` vs `filter`).
    """
    params = {"group": group, "includeSchemas": True}
    if action:
        params["action"] = action
    return call_tool("discover_tools", params)


_OWNER = os.getenv("GITHUB_OWNER", "user-bcp-student41")
_REPO  = os.getenv("GITHUB_REPO",  "hackaton-grupo-08")


def _normalize_labels(labels) -> list[str]:
    if not isinstance(labels, list):
        return []
    normalized = []
    for label in labels:
        value = label.get("name") or label.get("label") or "" if isinstance(label, dict) else label
        value = str(value).strip()
        if value:
            normalized.append(value)
    return normalized


def _extract_acceptance_criteria(body: str) -> list[str]:
    """Extrae criterios de aceptación del body markdown de un Issue.

    Prioriza checkboxes (- [ ] / - [x]); si no hay, busca viñetas bajo un
    encabezado que mencione "criterios de aceptación" / "acceptance criteria".
    """
    if not body:
        return []

    checkboxes = re.findall(r"^\s*-\s*\[[ xX]\]\s*(.+)$", body, re.MULTILINE)
    if checkboxes:
        return [c.strip() for c in checkboxes]

    lines   = body.splitlines()
    grabbed = []
    in_section = False
    for line in lines:
        if re.search(r"criterios?\s+de\s+aceptaci[oó]n|acceptance\s+criteria", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.strip().startswith("#"):
                break
            m = re.match(r"\s*[-*]\s*(.+)", line)
            if m:
                grabbed.append(m.group(1).strip())
            elif line.strip() == "" and grabbed:
                break
    return grabbed


def get_feature(issue_number: int | str) -> dict:
    """Lee el feature brief desde el GitHub Issue vía MCP de proyectos.

    Helper sobre call_tool("manage_issues", {"action": "get", ...}).

    Retorna:
        {
            "title":               str,
            "description":         str,   # body del issue en markdown
            "acceptance_criteria": list[str],
        }
    """
    params = {"action": "get", "owner": _OWNER, "repo": _REPO}
    if isinstance(issue_number, str) and issue_number.startswith("I_"):
        params["issueId"] = issue_number
    else:
        params["issueNumber"] = issue_number
    result = call_tool("manage_issues", params)
    issue = result.get("issue", result) if isinstance(result, dict) else result
    body  = issue.get("body") or issue.get("description") or ""
    return {
        "title":               issue.get("title", ""),
        "description":         body,
        "acceptance_criteria": _extract_acceptance_criteria(body),
        "labels":              _normalize_labels(issue.get("labels", [])),
        "issue_number":        issue.get("number") or issue.get("issueNumber"),
        "issue_id":            issue.get("id") or issue.get("issueId"),
        "state":               issue.get("state", ""),
        "url":                 issue.get("html_url") or issue.get("url", ""),
    }


def list_issues() -> list[dict]:
    """Lista todos los issues/features del proyecto GitHub vía MCP.

    Llama a manage_issues (action "list") y retorna la lista:
        [{"number": 42, "title": "...", "state": "open"}, ...]

    Si el MCP retorna un dict con clave "items" o "issues", extrae la lista.
    """
    result = call_tool("manage_issues", {
        "action": "list",
        "owner":  _OWNER,
        "repo":   _REPO,
        "state":  "all",
        "limit":  100,
    })
    if isinstance(result, list):
        raw = result
    else:
        raw = result.get("issues", result.get("items", []))

    return [
        {
            "number": it.get("number"),
            "title":  it.get("title", "(sin título)"),
            "state":  it.get("state", ""),
            "labels": _normalize_labels(it.get("labels", [])),
        }
        for it in raw
    ]


# ── GitHub Projects (v2) — proyecto asignado + backlog ──────────────────────

def list_projects() -> list[dict]:
    """Lista los GitHub Projects (v2) visibles para el MCP.

    Llama a manage_project (action "list") y normaliza la respuesta:
        [{"id": "PVT_...", "title": "...", "number": 1, "closed": False}, ...]
    """
    result = call_tool("manage_project", {
        "action": "list", "owner": _OWNER, "status": "all", "limit": 100,
    })
    if isinstance(result, list):
        raw = result
    else:
        raw = result.get("projects", result.get("items", []))

    wanted = os.getenv("GITHUB_PROJECT_TITLE", "").strip() or "backlog-hackaton-grupo-08"

    return [
        {
            "id":     p.get("id"),
            "title":  p.get("title", p.get("name", "(sin título)")),
            "number": p.get("number"),
            "closed": bool(p.get("closed", p.get("status") == "closed")),
        }
        for p in raw
        if not wanted or p.get("title", p.get("name")) == wanted
    ]


def _normalize_project_item(it: dict) -> dict:
    """Normaliza un item de backlog de GitHub Projects a un formato uniforme.

    El shape exacto varía según el server MCP (list_items vs filter_items),
    así que se prueban varias claves posibles para cada campo.
    """
    content     = it.get("content") if isinstance(it.get("content"), dict) else {}
    field_values = it.get("fieldValues") if isinstance(it.get("fieldValues"), dict) else {}

    title = (
        it.get("title")
        or content.get("title")
        or field_values.get("Title")
        or "(sin título)"
    )
    number = (
        it.get("number")
        or it.get("issueNumber")
        or it.get("contentNumber")
        or content.get("number")
    )
    state = it.get("state") or content.get("state") or ""
    item_type = it.get("type") or it.get("contentType") or content.get("__typename") or "Issue"

    return {
        "id":         it.get("id"),
        "contentId":  it.get("contentId") or content.get("id"),
        "type":       item_type,
        "title":      title,
        "number":     number,
        "state":      state,
        "description": it.get("description") or it.get("body") or content.get("body", ""),
        "labels":     _normalize_labels(it.get("labels") or content.get("labels", [])),
        "url":        it.get("url") or content.get("url", ""),
    }


def list_project_items(project_id: str, limit: int = 100) -> list[dict]:
    """Lista el backlog (items) de un GitHub Project (v2) — features/tareas.

    Prueba filter_items (más completo: título, estado, labels) con las dos
    formas de parámetro documentadas para "sin filtro" (`filter: {}` y
    `filterQuery: ""`), y si ambas fallan cae a list_items — que siempre
    acepta solo projectId/limit pero no devuelve título.

    Cada intento fallido levanta RuntimeError gracias a la detección de
    "isError" en call_tool(), así que el fallback SÍ se ejecuta cuando
    corresponde (antes se tragaba el error silenciosamente y devolvía backlog
    vacío aunque el proyecto tuviera items).

    Retorna: [{"id", "contentId", "type", "title", "number", "state"}, ...]
    """
    attempts = [
        {"action": "filter_items", "projectId": project_id, "filter": {}, "first": limit},
        {"action": "filter_items", "projectId": project_id, "filterQuery": "", "first": limit},
        {"action": "list_items",   "projectId": project_id, "limit": limit, "first": limit},
    ]

    result   = None
    last_exc = None
    for params in attempts:
        try:
            result = call_tool("manage_project", params)
            break
        except RuntimeError as exc:
            last_exc = exc
            continue

    if result is None:
        raise RuntimeError(f"[MCP Proyectos] No se pudo listar items del proyecto: {last_exc}")

    base_params = dict(params)
    items = []
    cursor = None
    while True:
        if isinstance(result, list):
            raw, page = result, {}
            structured = {}
        else:
            structured = result.get("structuredContent", {})
            raw = structured.get("items") or result.get("items") or []
            page = (
                structured.get("pageInfo") or result.get("pageInfo")
                or structured.get("pagination") or result.get("pagination") or {}
            )
        items.extend(raw)
        has_next = bool(page.get("hasNextPage", page.get("has_next_page", False)))
        next_cursor = page.get("endCursor") or page.get("end_cursor") or page.get("nextCursor")
        if not has_next:
            total_count = structured.get("totalCount", result.get("totalCount")) if isinstance(result, dict) else None
            if total_count and int(total_count) > len(items):
                raise RuntimeError(
                    "[MCP Proyectos] El proyecto tiene más items que los devueltos, pero el MCP no expuso cursor de paginación."
                )
            break
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("[MCP Proyectos] El MCP indicó otra página, pero no entregó un cursor válido.")
        cursor = next_cursor
        params = dict(base_params)
        params["after"] = cursor
        result = call_tool("manage_project", params)

    return [_normalize_project_item(it) for it in items]


def list_project_features(project_id: str, required_label: str | None = None) -> list[dict]:
    """Carga los Issues del proyecto, incluyendo su descripción, criterios y etiquetas."""
    features = []
    for item in list_project_items(project_id):
        if str(item.get("type", "")).lower() not in ("issue", ""):
            continue
        feature = get_feature_from_item(item)
        feature["issue_number"] = feature.get("issue_number") or item.get("number")
        feature["issue_id"] = feature.get("issue_id") or item.get("contentId")
        feature["labels"] = feature.get("labels") or item.get("labels", [])
        feature["state"] = feature.get("state") or item.get("state", "")
        feature["url"] = feature.get("url") or item.get("url", "")
        if required_label and required_label.casefold() not in {
            label.casefold() for label in feature.get("labels", [])
        }:
            continue
        features.append(feature)
    return features


def get_feature_from_item(item: dict) -> dict:
    """Resuelve el feature brief completo (título, body, criterios) a partir
    de un item de backlog de GitHub Projects.

    Usa contentId cuando el Project devuelve el ID de nodo del issue.
    Si no está disponible, conserva la resolución por número o título.
    """
    content_id = item.get("contentId") or item.get("content_id")
    if content_id and str(content_id).startswith("I_"):
        return get_feature(content_id)

    number = item.get("number")
    if number is None:
        for candidate in list_issues():
            if candidate.get("title") == item.get("title"):
                number = candidate.get("number")
                break

    if number is None:
        # El item de Projects v2 no tiene número de issue asociado
        # (puede ser un Draft Issue). Usamos los datos del propio item.
        title = item.get("title", "(sin título)")
        desc  = (
            item.get("description")
            or item.get("body")
            or f"Feature: {title}"
        )
        ac = item.get("acceptance_criteria", [])
        print(f"[MCP Proyectos] ⚠ Item sin número de issue — usando datos del proyecto directamente.")
        return {"title": title, "description": desc, "acceptance_criteria": ac}

    return get_feature(number)


def list_issue_comments(issue_number: int | str) -> list[dict]:
    """Lista los comentarios de un Issue y normaliza las formas comunes del MCP."""
    result = call_tool("manage_issues", {
        "action": "list_comments", "owner": _OWNER, "repo": _REPO,
        "issueNumber": int(issue_number), "perPage": 100,
    })
    if isinstance(result, list):
        comments = result
    else:
        comments = result.get("comments", result.get("items", []))
    return [
        {
            "body": str(comment.get("body") or comment.get("text") or ""),
            "author": comment.get("user", {}).get("login", "")
            if isinstance(comment.get("user"), dict) else str(comment.get("author", "")),
        }
        for comment in comments if isinstance(comment, dict)
    ]


def create_issue_comment(issue_number: int | str, body: str) -> dict:
    """Publica un comentario en un Issue; la aprobación humana la gestiona el caller."""
    return call_tool("manage_issues", {
        "action": "create_comment", "owner": _OWNER, "repo": _REPO,
        "issueNumber": int(issue_number), "body": body,
    })


# ── Publicación del backlog: etiquetas, Issues y asociación al proyecto ─────

def _unwrap(result):
    return result.get("issue", result) if isinstance(result, dict) else result


def expected_repo_url() -> str:
    return f"https://github.com/{_OWNER}/{_REPO}/issues/"


def list_repo_labels() -> set[str]:
    result = call_tool("manage_labels", {"action": "list", "limit": 100})
    labels = result if isinstance(result, list) else result.get("labels", result.get("items", []))
    return {str(label.get("name", "")) for label in labels if isinstance(label, dict)}


def ensure_labels(names: list[str], descriptions: dict[str, str] | None = None) -> list[str]:
    """Crea las etiquetas ausentes: el MCP descarta en silencio las que no existen al crear un Issue."""
    existing = {name.casefold() for name in list_repo_labels()}
    created = []
    for name in names:
        if name.casefold() in existing:
            continue
        call_tool("manage_labels", {"action": "create", "name": name,
                                    "description": (descriptions or {}).get(name, "")})
        created.append(name)
    return created


def find_issue_by_marker(marker: str) -> dict | None:
    """Busca un Issue (abierto o cerrado) cuyo cuerpo contenga la marca; sirve para no duplicar al reanudar."""
    result = call_tool("manage_issues", {"action": "list", "status": "all", "limit": 100})
    raw = result if isinstance(result, list) else result.get("issues", result.get("items", []))
    for issue in raw:
        if isinstance(issue, dict) and marker in str(issue.get("description") or issue.get("body") or ""):
            return {"id": issue.get("id"), "number": issue.get("number"), "url": issue.get("url", "")}
    return None


def create_issue(title: str, body: str, labels: list[str]) -> dict:
    """Crea un Issue y devuelve {id (nodo I_...), number, url, labels}; falla si cae en otro repositorio."""
    created = _unwrap(call_tool("manage_issues", {
        "action": "create", "title": title, "description": body, "labels": labels,
    }))
    issue = {"id": created.get("id"), "number": created.get("number"),
             "url": created.get("url", ""), "labels": created.get("labels", [])}
    if not issue["id"] or not issue["number"]:
        raise RuntimeError(f"[MCP Proyectos] Respuesta inesperada al crear el Issue: {created}")
    if issue["url"] and not issue["url"].startswith(expected_repo_url()):
        raise RuntimeError(
            f"[MCP Proyectos] El Issue #{issue['number']} se creó en {issue['url']}, no en "
            f"{_OWNER}/{_REPO}. Reinicia el MCP con GITHUB_OWNER/GITHUB_REPO correctos.")
    return issue


def add_issue_to_project(project_id: str, issue_node_id: str) -> dict:
    """Asocia un Issue (id de nodo I_...) a un GitHub Project v2; repetirlo sobre el mismo Issue es inocuo."""
    return call_tool("manage_project", {
        "action": "add_item", "projectId": project_id, "contentId": issue_node_id, "contentType": "issue",
    })


def verify_target_repo() -> None:
    """Aborta si el MCP está configurado para otro repositorio; el destino lo fija su entorno, no los parámetros."""
    result = call_tool("manage_issues", {"action": "list", "status": "all", "limit": 5})
    raw = result if isinstance(result, list) else result.get("issues", result.get("items", []))
    for issue in raw:
        url = str(issue.get("url", "")) if isinstance(issue, dict) else ""
        if url and not url.startswith(expected_repo_url()):
            raise RuntimeError(
                f"[MCP Proyectos] El MCP apunta a otro repositorio ({url}); se esperaba {_OWNER}/{_REPO}. "
                "Reinicia el MCP con GITHUB_OWNER/GITHUB_REPO correctos.")
