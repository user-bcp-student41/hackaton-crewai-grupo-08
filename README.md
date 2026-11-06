# CrewAI para equipos

Los agentes parten con instrucciones básicas. Sigue [Mejora tu agente](MEJORA_TU_AGENTE.md) para completar el ejercicio y consultar resultados desde el portal.

Base de trabajo del Lab 4, S1. Lee una funcionalidad del backlog mediante MCP Projects
y genera una solución Quarkus 3.x y Angular 17 con seis agentes de CrewAI, o siete cuando el equipo activa Datos y persistencia.
Cada agente tiene su definición y la tarea en un archivo propio.

## Editar tu agente

Los agentes son básicos: un objetivo breve, una responsabilidad por rol y una salida concreta.
Usa un requisito pequeño, por ejemplo crear una tarea con título.
Ajusta ese ejemplo al requisito del backlog de tu equipo.
Testing propone un caso válido y otro inválido; Security revisa entradas y secretos;
Chapter compara las entregas con el requisito. Los prompts conservan los formatos
que necesita el flujo para guardar código y revisar resultados.

Cada participante edita el archivo de su rol:

- `agents/architect.py`
- `agents/backend.py`
- `agents/frontend.py`
- `agents/testing.py`
- `agents/security.py`
- `agents/chapter.py`

El orden es `architect → backend → frontend → testing → security → chapter`.
Chapter reemplaza al LT como revisor final. La aprobación humana se conserva entre etapas.
Consulta [TEAM.md](TEAM.md) para crear el repo de tu equipo y repartir los archivos.

## Preparar el entorno

Requiere Python 3.11 a 3.13, Git y acceso a GitHub Copilot.
Usa Python 3.12 durante el taller y ejecuta los comandos en Bash. En Windows, abre Git Bash.

```bash
python -m venv .venv
if [ -f .venv/Scripts/activate ]; then
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi
python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
```

Si en macOS o Linux tu instalación se llama `python3.12`, úsala para crear el entorno. Una vez activado, ejecuta `python`.

Instala [Copilot CLI](https://github.com/features/copilot/cli), abre `copilot` y ejecuta `/login`.
El SDK usa esa sesión con `COPILOT_USE_LOGGED_IN_USER=true`.
El modelo predeterminado es `gpt-6-luna` con esfuerzo `high`. Cada llamada consume uso del plan de Copilot.
Puedes descargar su runtime antes del taller con `python -m copilot download-runtime`.

## Conectar el backlog

El proyecto configurado es `backlog-hackaton-grupo-08`, del owner `user-bcp-student41`,
en el repo `hackaton-grupo-08`. `PROJECTS_MCP_URL` y `PROJECTS_MCP_API_KEY` apuntan
al servicio MCP. Reinícialo con el repo correcto si ya estaba iniciado con otra configuración.

Si usas el MCP local del Lab 4 en Windows PowerShell, levántalo desde la raíz del repo:

```powershell
.\support\mcp-local\start-mcp.ps1
```

El script usa el owner y repo solicitados por defecto; se pueden cambiar con `-Owner` y `-Repo`.
Ese servicio requiere la imagen `localhost/mcp-github-project-manager:latest`, preparada por el instructor, y Podman o Docker. Si no tienes esa imagen, solicita al instructor un endpoint MCP del taller.
En macOS o Linux:

```sh
cd support/mcp-local
gh auth refresh -s project
bash start-mcp.sh --owner user-bcp-student41 --repo hackaton-grupo-08
```

Mantén esa terminal Bash abierta y ejecuta `python main.py` en otra terminal desde la raíz del repo. La URL de S1 es `http://localhost:8081`.

## Ejecutar el Crew

Desde la raíz de este repo, con el entorno virtual activado, `main.py` presenta dos opciones:

1. Product Owner: lee el plan `plan-inicial-epica-hus.md` (configurable con `PO_PLAN_FILE`) en lugar de las Issues. Extrae HU-01, HU-02 y la extensión de colecta con sus criterios, alcance, requisitos transversales y supuestos, y genera una especificación por historia con aprobación humana. Después de una única confirmación crea las etiquetas `historia` y `extension` si faltan, crea una Issue por historia con los criterios como checklist y la especificación, y las asocia al proyecto. Puedes publicar todo, solo las HU oficiales o nada. Es reanudable: no duplica Issues y solo reintenta lo que falló. Si el plan cambia, regenera las especificaciones pero no modifica las Issues ya creadas.
2. Desarrollo Full Stack: lista las Issues del proyecto para seleccionar una; ejecuta Arquitectura, Developer, Testing y Seguridad con aprobación humana por etapa. Arquitectura puede publicar su análisis como comentario de la Issue tras confirmación. Developer trabaja sobre un clon local y una rama `feature/<issue>-<slug>`.

`FEATURE_REPO` y `FEATURE_BASE_BRANCH` configuran el destino del PR (por defecto `user-bcp-student41/hackaton-grupo-08` y `main`). Tras aprobar las cuatro etapas, el flujo solicita confirmación final antes de hacer push y crear el PR.

### Permisos del Developer

El Developer edita el clon con herramientas propias (`list_files`, `read_file`, `search_text`, `write_file`, `replace_in_file`, `delete_path`, `run_command`). Dentro del workspace lee, crea, edita y elimina archivos sin preguntar. Lo demás se detiene y pregunta en la terminal (`s` una vez, `a` siempre durante la ejecución, `n` denegar) antes de seguir:

- Cualquier ruta fuera del workspace.
- Archivos con posibles credenciales (`.env*`, `*.pem`, `*.key`, `secret*`, `credential*`).
- Eliminar una carpeta con su contenido.
- Ejecutar un comando (por ejemplo `mvn test`): se muestra la línea completa y se ejecuta sin shell y sin variables que contengan `TOKEN`, `SECRET`, `PASSWORD` o `API_KEY`.

Si lo deniegas, la acción no se realiza y el Developer la declara pendiente. Nunca se permite `.git`, `git`, `gh` ni una shell: commit, push y PR solo los hace el flujo tras tu confirmación final. Los archivos del PR salen de `git` (sin `target/`, `node_modules/` ni credenciales) y `developer_permissions` en el checkpoint registra lo permitido y denegado.

Para iniciar:

```sh
python main.py
```

En las etapas de agentes puedes usar `s` para aprobar, `r` para reintentar con feedback,
o `n` para rechazar. Los checkpoints permiten retomar los pasos aprobados.

Los artefactos se guardan en `output/`:

- `product-owner/plan-<id>-<slug>/product_owner_spec.md`: especificación aprobada por historia del plan; al publicarla se copia también a `product-owner/issue-<n>-<slug>/`, que es la ruta que usa el flujo de desarrollo.
- `.product_owner_plan_checkpoint.json`: specs aprobadas y Issues publicadas (número, id y asociación al proyecto).
- `development/issue-<n>-<slug>/specs/`: arquitectura, implementación, pruebas y revisión de seguridad.
- `workspaces/feature-<n>-<slug>/`: clon local del repo en la rama de feature.
- Los archivos generados se escriben en las rutas relativas del repo clonado; el PR prepara solo los archivos generados y aprobados.

## Probar la solución generada

Con Java 21 y Maven instalados, ejecuta las pruebas desde el módulo backend del workspace clonado usando el comando que indique `testing_report.md`:

```sh
mvn test
mvn quarkus:dev
```

Con Node.js 18.19 o superior y npm, abre otra terminal en `output/frontend-angular`:

```sh
npm install
npm start
```

La API se inicia en `http://localhost:8080` y Angular en `http://localhost:4200`.
Revisa los comandos adicionales del informe de pruebas y registra sus resultados reales.

## Verificar cambios en los agentes

```sh
python tools/verify.py
```

Los checks recorren los seis roles, verifican artefactos, contexto y reanudación.
Sustituyen las llamadas al modelo y a MCP para ejecutarse sin credenciales.
La ejecución real de Copilot y MCP requiere el entorno del taller.

Consulta [SOURCE.md](SOURCE.md) para ver el origen de esta copia.

## Equipo de siete (solo CrewAI)

El grupo de siete añade un responsable de **Datos y persistencia**, que edita
únicamente `agents/data.py` y entrega su propio PR. Los equipos de seis mantienen
sus seis roles. En `team.json`, solo el equipo de siete añade `"data": "usuario-real"`
dentro de `roles`, con un usuario distinto de los otros responsables.

Antes de iniciar un flujo nuevo, el líder del equipo de siete configura
`CREWAI_INCLUDE_DATA=true` en su `.env`. El orden será Arquitectura → Datos y
persistencia → Backend → Frontend → Pruebas → Seguridad → Chapter. Cada etapa
mantiene aprobación, rechazo y reintento humanos. Datos produce `output/specs/data_spec.md`
y propuestas SQL en `output/db/`; no ejecuta migraciones. Backend usa ese contrato
y Chapter lo revisa. Los participantes mejoran las instrucciones iniciales de su agente.

Por defecto la variable es `false`. Un checkpoint de seis etapas no se reutiliza
en el flujo de siete ni viceversa: conserva la carpeta `output/` con otro nombre
antes de cambiar el modo. No borres evidencia previa para cambiar de flujo.
