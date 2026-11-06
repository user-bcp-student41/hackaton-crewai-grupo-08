"""S1 CrewAI — Generador BCP con HITL y checkpoint por paso.

Flujo:
  1. Conecta al MCP Projects → lista proyectos → elige proyecto → lista backlog → elige feature
  2. Por cada agente (Arquitecto, Backend, Frontend, Pruebas, Seguridad, Chapter), corre un mini-Crew de un solo paso.
  3. Tras cada paso muestra un preview y pide aprobación humana [s / n / r]:
       s = aprobar y continuar
       n = rechazar y abortar
       r = reintentar el mismo paso
  4. Al aprobar: guarda el artefacto inmediatamente (spec .md / código .java .ts .sql)
     y registra el checkpoint en output/.checkpoint.json.
  5. Al volver a ejecutar: carga el checkpoint y omite los pasos ya aprobados,
     inyectando sus outputs como contexto para los pasos restantes.

Estructura generada en output/:
  .checkpoint.json        ← estado de cada paso
  specs/
    user_story.md
    backend_spec.md
    frontend_spec.md
    chapter_review.md
  backend-quarkus/src/main/java/pe/bcp/<feature>/...
  frontend-angular/src/app/<feature>/...
  db/schema.sql  seed.sql
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import logging

# ---------------------------------------------------------------------------
# Telemetría configurable por entorno
# ---------------------------------------------------------------------------
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ["OTEL_LOG_LEVEL"] = "error"                # No ensucia la terminal con logs informativos
os.environ["OTEL_BSP_EXPORT_TIMEOUT"] = "2000"        # Reduce timeout de exportación a 2s (evita cuelgues al salir)

# Silenciar loggers que puedan imprimir advertencias de red/telemetría en stderr
for _log in ("opentelemetry", "crewai.telemetry", "urllib3", "requests"):
    logging.getLogger(_log).setLevel(logging.ERROR)


import re
import json
import time
import hashlib
import shutil
import threading
import textwrap
from pathlib import Path
from crewai import Crew, Process

from crew.workflow import build_tasks, include_data, workflow_steps
from agents.architect import agent as architect_agent
from agents import architect, developer, product_owner, security, testing
from crew import devops, plan_stories
# ── MCP clients ────────────────────────────────────────────────────
from mcp_projects import (
    list_tools as proj_tools,
    list_projects,
    list_project_items,
    list_project_features,
    list_issue_comments,
    create_issue_comment,
    ensure_labels,
    find_issue_by_marker,
    create_issue,
    add_issue_to_project,
    verify_target_repo,
    get_feature_from_item,
)
from hex_archetype import HEX_PROMPT_PREFIX

# ── Flag de verbosidad MCP ─────────────────────────────────────────
# True  → muestra el detalle de cada herramienta al arrancar
# False → solo confirma "Herramientas cargadas correctamente."
VERBOSE_MCP_TOOLS = False

# ── Scaffolding determinista para Backend y Frontend ────────────────
QUARKUS_POM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>pe.bcp</groupId>
    <artifactId>backend-quarkus</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <compiler-plugin.version>3.12.1</compiler-plugin.version>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
        <quarkus.platform.group-id>io.quarkus.platform</quarkus.platform.group-id>
        <quarkus.platform.version>3.8.3</quarkus.platform.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>${quarkus.platform.group-id}</groupId>
                <artifactId>${quarkus.platform.artifact-id}</artifactId>
                <version>${quarkus.platform.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-spring-web</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-spring-di</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-spring-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-resteasy-reactive-jackson</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-hibernate-validator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-jdbc-h2</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-jdbc-postgresql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.mindrot</groupId>
            <artifactId>jbcrypt</artifactId>
            <version>0.4</version>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-junit5</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>${quarkus.platform.group-id}</groupId>
                <artifactId>quarkus-maven-plugin</artifactId>
                <version>${quarkus.platform.version}</version>
                <extensions>true</extensions>
                <executions>
                    <execution>
                        <goals>
                            <goal>build</goal>
                            <goal>generate-code</goal>
                            <goal>generate-code-tests</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
"""

QUARKUS_APP_PROPS_TEMPLATE = """# BCP Quarkus Backend Configuration
quarkus.application.name=bcp-login-service
quarkus.http.port=8080

# CORS habilitado para el frontend Angular local
quarkus.http.cors=true
quarkus.http.cors.origins=http://localhost:4200,http://127.0.0.1:4200
quarkus.http.cors.headers=accept, authorization, content-type, x-requested-with
quarkus.http.cors.methods=GET, POST, PUT, DELETE, OPTIONS

# Base de datos H2 en memoria para pruebas instantáneas sin configuración externa
quarkus.datasource.db-kind=h2
quarkus.datasource.jdbc.url=jdbc:h2:mem:logindb;DB_CLOSE_DELAY=-1
quarkus.hibernate-orm.database.generation=drop-and-create
quarkus.hibernate-orm.log.sql=true
quarkus.log.level=INFO
"""

ANGULAR_PACKAGE_JSON = """{
  "name": "frontend-angular",
  "version": "1.0.0",
  "scripts": {
    "ng": "ng",
    "start": "ng serve",
    "build": "ng build",
    "watch": "ng build --watch --configuration development"
  },
  "private": true,
  "dependencies": {
    "@angular/animations": "^17.3.0",
    "@angular/common": "^17.3.0",
    "@angular/compiler": "^17.3.0",
    "@angular/core": "^17.3.0",
    "@angular/forms": "^17.3.0",
    "@angular/platform-browser": "^17.3.0",
    "@angular/platform-browser-dynamic": "^17.3.0",
    "@angular/router": "^17.3.0",
    "rxjs": "~7.8.0",
    "tslib": "^2.3.0",
    "zone.js": "~0.14.3"
  },
  "devDependencies": {
    "@angular-devkit/build-angular": "^17.3.0",
    "@angular/cli": "^17.3.0",
    "@angular/compiler-cli": "^17.3.0",
    "typescript": "~5.4.2"
  }
}
"""

ANGULAR_JSON = """{
  "$schema": "./node_modules/@angular/cli/lib/config/schema.json",
  "version": 1,
  "newProjectRoot": "projects",
  "projects": {
    "frontend-angular": {
      "projectType": "application",
      "root": "",
      "sourceRoot": "src",
      "prefix": "app",
      "architect": {
        "build": {
          "builder": "@angular-devkit/build-angular:application",
          "options": {
            "outputPath": "dist/frontend-angular",
            "index": "src/index.html",
            "browser": "src/main.ts",
            "polyfills": ["zone.js"],
            "tsConfig": "tsconfig.app.json",
            "styles": ["src/styles.css"]
          },
          "configurations": {
            "production": {
              "outputHashing": "all"
            },
            "development": {
              "optimization": false,
              "sourceMap": true
            }
          },
          "defaultConfiguration": "production"
        },
        "serve": {
          "builder": "@angular-devkit/build-angular:dev-server",
          "configurations": {
            "production": {
              "buildTarget": "frontend-angular:build:production"
            },
            "development": {
              "buildTarget": "frontend-angular:build:development"
            }
          },
          "defaultConfiguration": "development"
        }
      }
    }
  }
}
"""

ANGULAR_TSCONFIG_JSON = """{
  "compileOnSave": false,
  "compilerOptions": {
    "outDir": "./dist/out-tsc",
    "strict": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "experimentalDecorators": true,
    "moduleResolution": "node",
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ES2022", "dom"]
  }
}
"""

ANGULAR_TSCONFIG_APP_JSON = """{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "outDir": "./out-tsc/app",
    "types": []
  },
  "files": ["src/main.ts"],
  "include": ["src/**/*.d.ts"]
}
"""

ANGULAR_INDEX_HTML = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>BCP - Portal de Autenticación</title>
  <base href="/">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
  <app-root></app-root>
</body>
</html>
"""

ANGULAR_STYLES_CSS = """* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', sans-serif;
  background: linear-gradient(135deg, #0b1f3a 0%, #002a66 50%, #0a438c 100%);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
}
"""

ANGULAR_MAIN_TS = """import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptorsFromDi())
  ]
}).catch(err => console.error(err));
"""

# El codigo de aplicacion (app.component.ts, app.routes.ts, el .css del
# componente y UserRepository.java) lo genera el modelo: depende del feature.
# Aca solo queda el andamiaje de build, que ningun agente tiene que escribir.


def ensure_scaffolding(output_dir: Path) -> None:
    """
    Escribe sólo el andamiaje de build: pom.xml y application.properties de
    Quarkus, y package.json / angular.json / tsconfig / index.html / main.ts de
    Angular. Nada de esto describe el feature, así que no se le pide al modelo.

    El código de aplicación —entidad, repositorio, servicio, componentes, rutas
    y estilos— lo genera el agente y lo escribe extract_and_save_code(). Si el
    agente no lo emite, el proyecto queda incompleto a propósito: es la señal
    de que el paso falló, no algo que el andamiaje deba tapar.
    """
    # 1. Backend Quarkus
    pom_path = output_dir / "backend-quarkus" / "pom.xml"
    if not pom_path.exists():
        pom_path.parent.mkdir(parents=True, exist_ok=True)
        pom_path.write_text(QUARKUS_POM_TEMPLATE, encoding="utf-8")
        print("  🏗️ Scaffolding Backend: generado pom.xml (Quarkus 3.x)")

    app_props_path = output_dir / "backend-quarkus" / "src" / "main" / "resources" / "application.properties"
    if not app_props_path.exists():
        app_props_path.parent.mkdir(parents=True, exist_ok=True)
        app_props_path.write_text(QUARKUS_APP_PROPS_TEMPLATE, encoding="utf-8")
        print("  🏗️ Scaffolding Backend: generado application.properties (CORS + H2)")

    # 2. Frontend Angular 17
    front_dir = output_dir / "frontend-angular"
    front_scaffold = {
        "package.json": ANGULAR_PACKAGE_JSON,
        "angular.json": ANGULAR_JSON,
        "tsconfig.json": ANGULAR_TSCONFIG_JSON,
        "tsconfig.app.json": ANGULAR_TSCONFIG_APP_JSON,
        "src/index.html": ANGULAR_INDEX_HTML,
        "src/styles.css": ANGULAR_STYLES_CSS,
        "src/main.ts": ANGULAR_MAIN_TS,
    }
    created_front = 0
    for rel_path, content in front_scaffold.items():
        file_path = front_dir / rel_path
        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            created_front += 1

    if created_front > 0:
        print(f"  🏗️ Scaffolding Frontend: generados {created_front} archivos base de Angular 17")


# ── Rutas base ─────────────────────────────────────────────────────
OUTPUT_DIR      = Path(__file__).parent / "output"
CHECKPOINT_FILE = OUTPUT_DIR / ".checkpoint.json"
OUTPUT_DIR.mkdir(exist_ok=True)   # lo necesita save_checkpoint()
# ensure_scaffolding() NO se llama aquí: escribiría en output/ con sólo importar
# el módulo, antes del MCP, del feature elegido y del primer agente.

# ── Mapa archivo → ruta destino ────────────────────────────────────
FILE_MAP = {
    "User.java":               "backend-quarkus/src/main/java/pe/bcp/login/model/User.java",
    "LoginRequest.java":       "backend-quarkus/src/main/java/pe/bcp/login/dto/LoginRequest.java",
    "AuthResponse.java":       "backend-quarkus/src/main/java/pe/bcp/login/dto/AuthResponse.java",
    "AuthService.java":        "backend-quarkus/src/main/java/pe/bcp/login/service/AuthService.java",
    "AuthResource.java":       "backend-quarkus/src/main/java/pe/bcp/login/resource/AuthResource.java",
    "pom.xml":                 "backend-quarkus/pom.xml",
    "application.properties":  "backend-quarkus/src/main/resources/application.properties",
    "models.ts":               "frontend-angular/src/app/auth/models.ts",
    "auth.service.ts":         "frontend-angular/src/app/auth/auth.service.ts",
    "auth.guard.ts":           "frontend-angular/src/app/auth/auth.guard.ts",
    "login.component.ts":      "frontend-angular/src/app/auth/login.component.ts",
    "login.component.html":    "frontend-angular/src/app/auth/login.component.html",
    "auth.interceptor.ts":     "frontend-angular/src/app/core/auth.interceptor.ts",
    "app.component.ts":        "frontend-angular/src/app/app.component.ts",
    "app.routes.ts":           "frontend-angular/src/app/app.routes.ts",
    "login.component.css":     "frontend-angular/src/app/auth/login.component.css",
    "UserRepository.java":     "backend-quarkus/src/main/java/pe/bcp/login/repository/UserRepository.java",
    "schema.sql":              "db/schema.sql",
    "seed.sql":                "db/seed.sql",
}

# ── Checkpoint ─────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Carga el checkpoint si existe, o retorna estado vacío."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"steps": {}}


def save_checkpoint(data: dict) -> None:
    """Persiste el checkpoint en disco de forma segura."""
    try:
        clean_data = {}
        for k, v in data.items():
            if k == "steps" and isinstance(v, dict):
                clean_steps = {}
                for sk, sv in v.items():
                    if isinstance(sv, dict):
                        clean_steps[sk] = {
                            "status": sv.get("status"),
                            "output": str(getattr(sv.get("output"), "raw", sv.get("output")) or "")
                        }
                    else:
                        clean_steps[sk] = str(sv)
                clean_data[k] = clean_steps
            else:
                clean_data[k] = v
        CHECKPOINT_FILE.write_text(json.dumps(clean_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  ⚠ Advertencia al guardar checkpoint: {e}")


# ── Output helpers ─────────────────────────────────────────────────

def extract_and_save_code(text) -> list[str]:
    """Extrae bloques de código del output del LLM y los guarda en sus carpetas correspondientes."""
    text_str = str(getattr(text, "raw", text) or "")
    saved = []
    seen_paths = set()

    # Patrón para bloques ``` con o sin lenguaje
    code_block_pattern = re.compile(
        r"(?:(?:archivo|file|fichero|clase|class|componente)?[:\s*#/-]*[`\"]?([a-zA-Z0-9_.\-/]+\.(?:java|ts|html|css|sql|xml|properties))[`\"]?[^\n]*\n)?"
        r"```(?:[a-zA-Z0-9_\-]+)?\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )

    for m in code_block_pattern.finditer(text_str):
        name = m.group(1)
        code = m.group(2).strip()
        if not code:
            continue

        target_name = name

        # 1. Buscar nombre en las primeras líneas del bloque de código (incluyendo rutas con slashes)
        if not target_name:
            lines = code.split("\n")[:5]
            for l in lines:
                m_line = re.search(
                    r"(?:(?:\/\/|\/\*|#|<!--|--)\s*|\b)([a-zA-Z0-9_.\-/]+\.(?:java|ts|html|css|sql|xml|properties))\b",
                    l,
                    re.IGNORECASE,
                )
                if m_line:
                    target_name = m_line.group(1)
                    break

        # 2. Heurística según el contenido del código si no se detectó nombre explícito
        if not target_name:
            m_java = re.search(r"public\s+(?:class|interface|record|enum)\s+(\w+)", code)
            if m_java:
                target_name = f"{m_java.group(1)}.java"
            elif "CREATE TABLE" in code.upper():
                target_name = "schema.sql"
            elif "INSERT INTO" in code.upper():
                target_name = "seed.sql"
            elif re.search(r"export\s+class\s+(\w+Component)", code) or "@Component" in code:
                target_name = "login.component.ts"
            elif re.search(r"export\s+class\s+(\w+Service)", code) or ("@Injectable" in code and "service" in code.lower()):
                target_name = "auth.service.ts"
            elif re.search(r"export\s+class\s+(\w+Guard)", code) or "CanActivate" in code:
                target_name = "auth.guard.ts"
            elif "HttpInterceptor" in code or "Interceptor" in code:
                target_name = "auth.interceptor.ts"
            elif "export interface" in code or "export type" in code:
                target_name = "models.ts"
            elif "<form" in code.lower() or ("<button" in code.lower() and "<div" in code.lower()):
                target_name = "login.component.html"

        if not target_name:
            continue

        # Extraer solo el nombre base del archivo
        target_name = Path(target_name.strip()).name

        # Mapeo a ruta destino
        dest_rel = FILE_MAP.get(target_name)
        if not dest_rel:
            lname = target_name.lower()
            if target_name.endswith(".java"):
                if "test" in lname or "@test" in code.lower():
                    dest_rel = f"backend-quarkus/src/test/java/pe/bcp/login/{target_name}"
                elif "service" in lname:
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/service/{target_name}"
                elif "resource" in lname or "controller" in lname or "@path" in code.lower():
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/resource/{target_name}"
                elif "repository" in lname or "dao" in lname:
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/repository/{target_name}"
                elif "request" in lname or "response" in lname or "dto" in lname:
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/dto/{target_name}"
                elif "model" in lname or "entity" in lname or "@entity" in code.lower():
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/model/{target_name}"
                else:
                    # Por defecto clasificar como modelo de dominio
                    dest_rel = f"backend-quarkus/src/main/java/pe/bcp/login/model/{target_name}"
            elif target_name.endswith(".ts"):
                if "interceptor" in lname:
                    dest_rel = f"frontend-angular/src/app/core/{target_name}"
                elif "guard" in lname:
                    dest_rel = f"frontend-angular/src/app/auth/{target_name}"
                elif "service" in lname:
                    dest_rel = f"frontend-angular/src/app/auth/{target_name}"
                elif "component" in lname:
                    dest_rel = f"frontend-angular/src/app/auth/{target_name}"
                else:
                    dest_rel = f"frontend-angular/src/app/auth/{target_name}"
            elif target_name.endswith(".html"):
                dest_rel = f"frontend-angular/src/app/auth/{target_name}"
            elif target_name.endswith(".css"):
                dest_rel = f"frontend-angular/src/app/auth/{target_name}"
            elif target_name.endswith(".sql"):
                dest_rel = f"db/{target_name}"
            elif target_name.endswith(".properties"):
                dest_rel = f"backend-quarkus/src/main/resources/{target_name}"
            elif target_name == "pom.xml":
                dest_rel = f"backend-quarkus/{target_name}"

        if dest_rel and dest_rel not in seen_paths:
            seen_paths.add(dest_rel)

            # Normalización automática para garantizar compilabilidad directa
            if dest_rel.endswith("models.ts"):
                code = re.sub(r'^(interface\s+)', r'export \1', code, flags=re.MULTILINE)
            elif dest_rel.endswith(".java") and not re.search(r'^\s*package\s+', code, flags=re.MULTILINE):
                if "/model/" in dest_rel:
                    pkg = "pe.bcp.login.model"
                elif "/service/" in dest_rel:
                    pkg = "pe.bcp.login.service"
                elif "/resource/" in dest_rel:
                    pkg = "pe.bcp.login.resource"
                elif "/repository/" in dest_rel:
                    pkg = "pe.bcp.login.repository"
                elif "/dto/" in dest_rel:
                    pkg = "pe.bcp.login.dto"
                else:
                    pkg = "pe.bcp.login"
                code = f"package {pkg};\n\n" + code

            dest = OUTPUT_DIR / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(code, encoding="utf-8")
            saved.append(dest_rel)
            print(f"  💾 Guardado: {dest_rel}")

    if not saved:
        print("  ⚠ Advertencia: no se detectaron archivos de código fuente para extraer en este paso.")
    else:
        print(f"  📦 Total archivos de código generados en este paso: {len(saved)}")

    # Asegurar que el andamiaje base exista siempre
    ensure_scaffolding(OUTPUT_DIR)

    return saved


def save_spec(filename: str, content) -> None:
    specs_dir = OUTPUT_DIR / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    text = str(getattr(content, "raw", content) or "")
    (specs_dir / filename).write_text(text, encoding="utf-8")
    print(f"  ✅ specs/{filename}")


# ── Mini-Crew: corre un único agente/tarea ─────────────────────────

class StepLoadingSpinner:
    """Indicador de carga interactivo con spinner y tiempo transcurrido en tiempo real."""
    def __init__(self, message: str = "Agente procesando con el LLM..."):
        self.message = message
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = None

    def pause(self) -> None:
        self.paused.set()
        time.sleep(0.3)  # deja terminar el último repintado antes de escribir la pregunta
        try:
            sys.stdout.write("\r" + " " * 75 + "\r")
            sys.stdout.flush()
        except Exception:
            pass

    def resume(self) -> None:
        self.paused.clear()

    def _spin(self):
        chars = ["|", "/", "-", "\\"]
        idx = 0
        t0 = time.time()
        # Pequeña pausa inicial para que CrewAI imprima sus recuadros iniciales
        time.sleep(1.0)
        while not self.stop_event.is_set():
            if self.paused.is_set():
                time.sleep(0.1)
                continue
            elapsed = int(time.time() - t0)
            mins, secs = divmod(elapsed, 60)
            time_str = f"{mins:02d}:{secs:02d}"
            char = chars[idx % len(chars)]
            msg = f"\r  ⏳ [{char}] {self.message} ({time_str} transcurrido)   "
            try:
                sys.stdout.write(msg)
                sys.stdout.flush()
            except Exception:
                pass
            idx += 1
            time.sleep(0.2)
        try:
            sys.stdout.write("\r" + " " * 75 + "\r")
            sys.stdout.flush()
        except Exception:
            pass

    def __enter__(self):
        global _ACTIVE_SPINNER
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
        _ACTIVE_SPINNER = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _ACTIVE_SPINNER
        _ACTIVE_SPINNER = None
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)


_ACTIVE_SPINNER = None


def run_step(agent, task) -> str:
    """Ejecuta un mini-Crew de un solo agente y retorna el output en texto."""
    mini_crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        tracing=False,
    )
    with StepLoadingSpinner(f"Generando con {agent.llm.model}..."):
        result = mini_crew.kickoff()

    # Pausa para permitir que los callbacks y paneles asíncronos de CrewAI terminen de pintar en consola
    time.sleep(1.2)

    if hasattr(result, "raw") and result.raw:
        return str(result.raw)
    if hasattr(task, "output") and task.output:
        return str(getattr(task.output, "raw", task.output))
    return str(result)


# ── HITL: aprobación humana ────────────────────────────────────────

def _flush_input_buffer():
    """Limpia caracteres tecleados accidentalmente mientras el LLM generaba."""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except Exception:
        pass


def print_formatted_preview(step_name: str, output: str, max_lines: int = 45) -> None:
    """Muestra el preview con formato enriquecido (tablas redondeadas alineadas, colores, preservando saltos de línea)."""
    output_str = str(getattr(output, "raw", output) or "").strip()
    if not output_str:
        print("  (Sin contenido generado)")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.box import ROUNDED

        console = Console()
        console.print(f"\n[bold cyan]{'─'*65}[/bold cyan]")
        console.print(f"[bold cyan]▶ OUTPUT GENERADO — {step_name}[/bold cyan]")
        console.print(f"[bold cyan]{'─'*65}[/bold cyan]\n")

        all_lines = output_str.splitlines()
        lines = all_lines[:max_lines]
        hidden_count = max(0, len(all_lines) - max_lines)

        table_lines = []
        in_table = False
        non_table_buffer = []

        def flush_buf():
            if non_table_buffer:
                console.print("\n".join(non_table_buffer))
                non_table_buffer.clear()

        def render_table(tbl_lines):
            if len(tbl_lines) < 2:
                for tl in tbl_lines:
                    console.print(tl)
                return
            headers = [c.strip() for c in tbl_lines[0].split("|")[1:-1]]
            if not headers:
                for tl in tbl_lines:
                    console.print(tl)
                return
            table = Table(show_header=True, header_style="bold magenta", box=ROUNDED, expand=True)
            for i, h in enumerate(headers):
                if i == 0:
                    table.add_column(h, style="cyan", ratio=3)
                elif i == 1 and any(k in h.lower() for k in ("estado", "status", "resultado")):
                    table.add_column(h, justify="center", ratio=1)
                else:
                    table.add_column(h, style="white", ratio=4)

            # Las filas de datos comienzan tras el separador | --- |
            for r in tbl_lines[2:]:
                cols = [c.strip() for c in r.split("|")[1:-1]]
                if len(cols) == len(headers):
                    table.add_row(*cols)
                elif cols:
                    while len(cols) < len(headers):
                        cols.append("")
                    table.add_row(*cols[:len(headers)])
            console.print(table)

        for line in lines:
            st = line.strip()
            if st.startswith("|") and st.endswith("|") and st.count("|") >= 2:
                if not in_table:
                    flush_buf()
                    in_table = True
                table_lines.append(st)
            else:
                if in_table:
                    render_table(table_lines)
                    table_lines.clear()
                    in_table = False
                non_table_buffer.append(line)

        if in_table:
            render_table(table_lines)
        flush_buf()

        if hidden_count > 0:
            console.print(f"\n[dim italic]... [{hidden_count} líneas adicionales guardadas en specs/ y código][/dim italic]")

        console.print(f"\n[bold cyan]{'─'*65}[/bold cyan]")

    except Exception:
        # Fallback sin formato especial si falla Rich
        sep = "─" * 65
        print(f"\n{sep}\n▶ OUTPUT GENERADO — {step_name}\n{sep}")
        print("\n".join(output_str.splitlines()[:max_lines]))
        print(sep)


def hitl_approve(step_name: str, output: str) -> tuple[str, str]:
    """
    Muestra un preview del output y pide aprobación de forma clara e interactiva.

    Retorna:
        ("s", "")         → aprobado
        ("n", "")         → rechazado (abortar)
        ("r", feedback)   → reintentar el paso (con feedback opcional del usuario)
    """
    import time
    time.sleep(0.3)

    print_formatted_preview(step_name, output)

    box_line = "=" * 65
    banner = f"""
{box_line}
 🔔 ACCIÓN REQUERIDA — Aprobación humana para: {step_name}
{box_line}
 [s] = Aprobar y continuar al siguiente paso
 [r] = Reintentar este mismo paso (permite ingresar feedback opcional)
 [n] = Rechazar y detener ejecución
{box_line}"""
    print(banner)

    while True:
        _flush_input_buffer()
        try:
            raw = input("\n👉 Ingresa tu opción [s/r/n] y presiona Enter: ").strip().lower()
        except EOFError:
            return "n", ""
        except KeyboardInterrupt:
            print("\n❌ Interrupción por teclado.")
            return "n", ""

        tokens = raw.split()
        choice = tokens[-1] if tokens else ""

        if not choice:
            continue

        if choice in ("s", "si", "sí", "y", "yes", "1") or choice.endswith("s"):
            return "s", ""
        if choice in ("n", "no", "0") or choice.endswith("n"):
            return "n", ""
        if choice in ("r", "retry", "reintentar") or choice.endswith("r"):
            print("\n💬 [Feedback Opcional] Escribe instrucciones adicionales para el agente")
            feedback = input("   (o presiona Enter para reintentar sin cambios): ").strip()
            return "r", feedback

        print("\n  ✗ Opción inválida. Por favor ingresa 's' para sí, 'r' para reintentar o 'n' para rechazar.")



# ── Contexto acumulado ─────────────────────────────────────────────

def _ctx_snippet(text: str, max_chars: int = 8000) -> str:
    """Recorta el output a max_chars para inyectarlo como contexto."""
    text_clean = str(text or "").strip()
    if len(text_clean) <= max_chars:
        return text_clean
    return text_clean[:max_chars] + "\n...(truncado para contexto)"


def build_context_note(approved_outputs: dict) -> str:
    """Construye una nota de contexto con los outputs aprobados anteriores."""
    parts = []
    labels = {key: label for key, label, *_ in workflow_steps(True)}
    for key, label in labels.items():
        if key in approved_outputs:
            val = str(getattr(approved_outputs[key], "raw", approved_outputs[key]) or "")
            parts.append(f"### {label}\n{_ctx_snippet(val)}")
    if not parts:
        return ""
    return "\n\n---\n## Contexto de pasos anteriores\n\n" + "\n\n".join(parts)



# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def _legacy_main():
    with_data = include_data()
    steps = workflow_steps(with_data)
    # ── MCP Proyectos: descubrir tools ────────────────────────────────
    print("\n[MCP Proyectos] Autenticando...")
    _proj_tools = proj_tools()
    if VERBOSE_MCP_TOOLS:
        print("[MCP Proyectos] Herramientas disponibles:")
        for t in _proj_tools:
            print(f"  · {t['name']}: {t['description']}")
    else:
        print("[MCP Proyectos] Herramientas cargadas correctamente.")

    # ── Selección de proyecto ─────────────────────────────────────────
    projects = list_projects()
    if not projects:
        print("[MCP Proyectos] ✗ No se encontraron proyectos.")
        raise SystemExit(1)

    if len(projects) == 1:
        selected_project = projects[0]
        print(f"\n[MCP Proyectos] Proyecto asignado: {selected_project['title']}")
    else:
        print("\n[MCP Proyectos] Proyectos disponibles:")
        for i, proj in enumerate(projects, 1):
            icon = "⚫" if proj.get("closed") else "🟢"
            print(f"  {i}. {icon} {proj.get('title', '(sin título)')}")
        while True:
            sel = input(f"\nSelecciona el número de proyecto [1-{len(projects)}]: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(projects):
                selected_project = projects[int(sel) - 1]
                break
            print(f"  ✗ Entrada inválida.")

    # ── Selección de feature del backlog ─────────────────────────────
    backlog = list_project_items(selected_project["id"])
    if not backlog:
        print("[MCP Proyectos] ✗ El proyecto no tiene items en el backlog.")
        raise SystemExit(1)

    print(f"\n[MCP Proyectos] Backlog de '{selected_project['title']}':")
    for i, item in enumerate(backlog, 1):
        icon = "⚫" if item.get("state", "").lower() == "closed" else "🟢"
        num  = f"#{item['number']} — " if item.get("number") else ""
        print(f"  {i}. {icon} {num}{item.get('title', '(sin título)')}")

    while True:
        sel = input(f"\nSelecciona el número de feature [1-{len(backlog)}]: ").strip()
        if sel.isdigit() and 1 <= int(sel) <= len(backlog):
            selected_item = backlog[int(sel) - 1]
            break
        print(f"  ✗ Entrada inválida.")

    feature = get_feature_from_item(selected_item)
    print(f"\n[MCP Proyectos] Feature cargado: {feature['title']}")
    print(f"[MCP Proyectos] Criterios de aceptación: {feature['acceptance_criteria']}")

    # ── Cargar checkpoint ─────────────────────────────────────────────
    checkpoint  = load_checkpoint()
    steps_state = checkpoint.get("steps", {})

    # Verificar si el checkpoint corresponde a este feature (por título)
    ckpt_feature = checkpoint.get("feature_title")
    if ckpt_feature and ckpt_feature != feature["title"]:
        print(f"\n⚠  El checkpoint existente es para '{ckpt_feature}'.")
        ans = input("¿Ignorar checkpoint y empezar desde cero? [s/n]: ").strip().lower()
        if ans == "s":
            steps_state = {}
            checkpoint  = {"steps": {}}
        else:
            print("Abortando. Cambia de feature o elimina output/.checkpoint.json para reiniciar.")
            raise SystemExit(0)

    mode = "with-data" if with_data else "standard"
    previous_mode = checkpoint.get("workflow_mode", "standard")
    if steps_state and previous_mode != mode:
        print("El checkpoint pertenece a otro flujo. Conserva output/ moviéndolo a otra carpeta antes de cambiar CREWAI_INCLUDE_DATA.")
        raise SystemExit(1)
    checkpoint["workflow_mode"] = mode
    checkpoint["feature_title"] = feature["title"]

    # ── Recuperar outputs aprobados del checkpoint ────────────────────
    approved_outputs: dict = {}
    for step_key, step_data in steps_state.items():
        if step_data.get("status") == "approved":
            approved_outputs[step_key] = step_data.get("output", "")

    # ── Enriquecer backstory del Chapter con brief del feature ────────
    architect_agent.backstory += HEX_PROMPT_PREFIX + (
        f"\n\n## Feature brief\n"
        f"**{feature['title']}**\n\n{feature['description']}\n\n"
        f"**Criterios de aceptación:** {', '.join(feature['acceptance_criteria'])}"
    )

    # ── Definición de pasos ───────────────────────────────────────────
    # (key, label, agent, spec_filename, extraer_código)


    # Andamiaje de build: en este punto, con proyecto y feature ya elegidos.
    ensure_scaffolding(OUTPUT_DIR)

    print("\n" + "=" * 60)
    print(f"S1 CrewAI — HITL — Feature: {feature['title']}")
    print("Pasos: " + " → ".join(step[1] for step in steps))
    print("=" * 60)

    # ── Loop HITL ─────────────────────────────────────────────────────
    for step_key, step_label, agent, spec_file, do_code in steps:

        # ── Ya aprobado en ejecución anterior → omitir ───────────────
        if steps_state.get(step_key, {}).get("status") == "approved":
            print(f"\n✅ [{step_label}] — ya aprobado (checkpoint). Omitiendo.")
            if do_code:
                saved_out = steps_state[step_key].get("output", "")
                if saved_out:
                    extract_and_save_code(saved_out)
            continue

        print(f"\n{'─'*60}")
        print(f"▶ PASO: {step_label}")
        print(f"{'─'*60}")

        # ── Bucle de reintentos ───────────────────────────────────────
        user_feedback = ""
        while True:
            # Rebuild tasks fresh en cada intento
            task_map = build_tasks(feature, with_data)
            task = task_map[step_key]

            # Inyectar contexto de pasos anteriores en la descripción
            ctx_note = build_context_note(approved_outputs)
            if ctx_note:
                task.description = task.description + ctx_note

            if with_data and step_key == "backend":
                task.description += "\nUsa el diseño de persistencia aprobado de Datos y persistencia. No regeneres sus archivos SQL; implementa el acceso a datos según ese contrato."
            if with_data and step_key == "chapter":
                task.description += "\nRevisa también el modelo, migración y compatibilidad del contrato aprobado de Datos y persistencia con backend."

            # Si el usuario ingresó feedback opcional en un reintento, inyectarlo como directiva prioritaria
            if user_feedback:
                task.description += (
                    f"\n\n---\n## ⚠️ INSTRUCCIONES ESPECÍFICAS DE CORRECCIÓN (FEEDBACK HUMANO):\n"
                    f"{user_feedback}\n"
                    f"Por favor atiende y corrige con máxima prioridad las observaciones del usuario indicadas arriba.\n"
                )

            # Ejecutar mini-Crew
            output = run_step(agent, task)

            # HITL
            decision, user_feedback = hitl_approve(step_label, output)

            if decision == "s":
                # APROBADO
                print(f"\n✅ {step_label} aprobado. Guardando artefactos...")
                save_spec(spec_file, output)
                if do_code:
                    extract_and_save_code(output)
                approved_outputs[step_key] = output
                steps_state[step_key] = {"status": "approved", "output": output}
                checkpoint["steps"] = steps_state
                save_checkpoint(checkpoint)
                break

            elif decision == "n":
                # RECHAZADO
                print(f"\n❌ {step_label} rechazado. Abortando ejecución.")
                steps_state[step_key] = {"status": "rejected", "output": output}
                checkpoint["steps"] = steps_state
                save_checkpoint(checkpoint)
                raise SystemExit(0)

            else:
                # REINTENTAR
                if user_feedback:
                    print(f"\n🔄 Reintentando {step_label} incorporando tu feedback: \"{user_feedback}\"...")
                else:
                    print(f"\n🔄 Reintentando {step_label}...")
                # el while True vuelve a ejecutar el paso

    # ── Todos los pasos aprobados ─────────────────────────────────────
    chapter_text = str(getattr(approved_outputs.get("chapter", ""), "raw", approved_outputs.get("chapter", "")) or "")

    print("\n" + "=" * 60)
    print("✅ TODOS LOS PASOS APROBADOS")
    print("=" * 60)
    print("  output/specs/            → " + " · ".join(step[3] for step in steps))
    print("  output/backend-quarkus/  → archivos .java extraídos")
    print("  output/frontend-angular/ → archivos .ts/.html extraídos")
    print("  output/db/               → .sql extraídos")
    print("=" * 60)
    print("\nVEREDICTO del Chapter (extracto):")
    print(chapter_text[-500:] if len(chapter_text) > 500 else chapter_text)

    if devops.enabled():
        checkpoint["published"] = devops.publish(OUTPUT_DIR, feature, chapter_text, checkpoint.get("published", {}))
        save_checkpoint(checkpoint)


def _feature_slug(feature: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(feature.get("title", "feature")).lower()).strip("-")[:40] or "feature"


def _feature_key(feature: dict) -> str:
    identifier = feature.get("issue_number") or feature.get("issue_id") or _feature_slug(feature)
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(identifier)).strip("-") or "feature"


def _po_spec_relative_path(feature: dict) -> str:
    issue = feature.get("issue_number")
    prefix = f"issue-{issue}-" if issue else "issue-"
    return f"product-owner/{prefix}{_feature_slug(feature)}/product_owner_spec.md"


def _plan_spec_relative_path(feature: dict) -> str:
    return f"product-owner/plan-{str(feature['plan_id']).lower()}-{_feature_slug(feature)}/product_owner_spec.md"


def _plan_path() -> Path:
    configured = Path(os.getenv("PO_PLAN_FILE", "").strip() or "plan-inicial-epica-hus.md")
    return configured if configured.is_absolute() else Path(__file__).parent / configured


def _load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default.copy()
    except (OSError, json.JSONDecodeError):
        return default.copy()


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _select_item(items: list[dict], prompt: str) -> dict:
    while True:
        try:
            selection = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(0)
        if selection.isdigit() and 1 <= int(selection) <= len(items):
            return items[int(selection) - 1]
        print(f"Opción inválida. Elige un número entre 1 y {len(items)}.")


def _select_project(projects: list[dict]) -> dict:
    if not projects:
        raise SystemExit("No se encontró el proyecto configurado en el MCP.")
    if len(projects) == 1:
        return projects[0]
    print("\nProyectos disponibles:")
    for index, project in enumerate(projects, 1):
        print(f"  {index}. {project.get('title', '(sin título)')}")
    return _select_item(projects, f"Selecciona proyecto [1-{len(projects)}]: ")


def _print_features(features: list[dict]) -> None:
    for index, feature in enumerate(features, 1):
        number = feature.get("issue_number")
        labels = ", ".join(feature.get("labels", []))
        prefix = f"#{number} — " if number else ""
        suffix = f" [{labels}]" if labels else ""
        print(f"  {index}. {prefix}{feature.get('title', '(sin título)')}{suffix}")


PLAN_LABEL_DESCRIPTIONS = {
    "historia": "Historia de usuario definida en el plan de trabajo",
    "extension": "Extensión opcional definida en el plan de trabajo",
}


def _choose_publication(pending: list[dict], project: dict) -> list[dict]:
    """Una sola confirmación: todas, solo las HU oficiales o ninguna."""
    repo = f"{os.getenv('GITHUB_OWNER', 'user-bcp-student41')}/{os.getenv('GITHUB_REPO', 'hackaton-grupo-08')}"
    print(f"\nPublicación en {repo} y proyecto '{project.get('title', '')}':")
    for feature in pending:
        print(f"  - {feature['title']}  [{', '.join(feature['labels'])}]")
    official = [feature for feature in pending if "extension" not in feature["labels"]]
    options = "[s] crear todas  [n] cancelar"
    if official and len(official) != len(pending):
        options = "[s] crear todas  [h] solo las HU oficiales  [n] cancelar"
    while True:
        try:
            answer = input(f"¿Crear estas Issues y asociarlas al proyecto? {options}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []
        if answer in ("s", "si", "sí", "y", "yes"):
            return pending
        if answer == "h" and official:
            return official
        if answer in ("n", "no"):
            return []
        print("  Opción inválida.")


def _publish_plan_stories(features: list[dict], project: dict, checkpoint: dict, checkpoint_path: Path,
                          source_name: str) -> None:
    """Crea las Issues y las asocia al proyecto; reanudable y sin duplicados."""
    published = checkpoint.setdefault("published", {})

    def done(feature: dict) -> bool:
        record = published.get(feature["plan_id"], {})
        return bool(record.get("number") and record.get("project_linked"))

    pending = [feature for feature in features if not done(feature)]
    if not pending:
        print("\nTodas las HUs ya están publicadas y asociadas al proyecto:")
        for feature in features:
            print(f"  - {feature['title']}: {published[feature['plan_id']].get('url', '')}")
        return
    chosen = _choose_publication(pending, project)
    if not chosen:
        print("Publicación cancelada. Las especificaciones quedaron guardadas; vuelve a ejecutar para publicar.")
        return
    try:
        verify_target_repo()
        created_labels = ensure_labels(sorted({label for f in chosen for label in f["labels"]}),
                                       PLAN_LABEL_DESCRIPTIONS)
    except Exception as error:
        print(f"No se pudo preparar la publicación: {error}")
        return
    if created_labels:
        print(f"Etiquetas creadas: {', '.join(created_labels)}")

    failures = []
    for feature in chosen:
        key = feature["plan_id"]
        record = published.setdefault(key, {})
        try:
            if not record.get("number"):
                spec = (OUTPUT_DIR / feature["product_owner_spec_path"]).read_text(encoding="utf-8")
                body = plan_stories.issue_body(feature["plan_story"], spec, source_name)
                issue = find_issue_by_marker(plan_stories.story_marker(key)) or create_issue(
                    feature["title"], body, feature["labels"])
                record.update(number=issue["number"], id=issue["id"], url=issue.get("url", ""))
                _save_json(checkpoint_path, checkpoint)
            if not record.get("project_linked"):
                add_issue_to_project(project["id"], record["id"])
                record["project_linked"] = True
                _save_json(checkpoint_path, checkpoint)
            issue_spec = OUTPUT_DIR / _po_spec_relative_path({**feature, "issue_number": record["number"]})
            issue_spec.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(OUTPUT_DIR / feature["product_owner_spec_path"], issue_spec)
            print(f"  ✓ #{record['number']} {feature['title']} → proyecto '{project.get('title', '')}'")
        except Exception as error:
            failures.append(key)
            print(f"  ✗ {feature['title']}: {error}")
    if failures:
        print(f"\nQuedaron pendientes: {', '.join(failures)}. Vuelve a ejecutar para reintentar sin duplicar.")


def run_product_owner_from_plan(project: dict) -> None:
    """Lee el plan, genera una spec aprobada por HU y las publica como Issues del proyecto."""
    plan_path = _plan_path()
    if not plan_path.is_file():
        print(f"No se encontró el plan: {plan_path}. Configura PO_PLAN_FILE o crea el archivo.")
        return
    text = plan_path.read_text(encoding="utf-8")
    parsed = plan_stories.parse_plan(text)
    if not parsed["stories"]:
        print(f"No se encontraron historias con criterios de aceptación en {plan_path.name}.")
        return
    features = [plan_stories.story_to_feature(story) for story in parsed["stories"]]
    for feature in features:
        feature["product_owner_spec_path"] = _plan_spec_relative_path(feature)

    checkpoint_path = OUTPUT_DIR / ".product_owner_plan_checkpoint.json"
    checkpoint = _load_json(checkpoint_path, {"steps": {}, "published": {}})
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if checkpoint.get("plan_sha256") not in (None, digest):
        print("El plan cambió desde la última ejecución: se regenerarán las especificaciones. "
              "Las Issues ya creadas no se modifican.")
        checkpoint["steps"] = {}
    checkpoint["plan_sha256"] = digest
    steps = checkpoint.setdefault("steps", {})
    print(f"\nProduct Owner: {len(features)} historia(s) leídas de {plan_path.name}")

    for feature in features:
        key = feature["plan_id"]
        spec_path = OUTPUT_DIR / feature["product_owner_spec_path"]
        if steps.get(key, {}).get("status") == "approved" and spec_path.is_file():
            print(f"  Aprobada previamente: {feature['title']}")
            continue
        label = f"Product Owner — {feature['title']}"
        feedback = ""
        while True:
            task = product_owner.build_task(feature, features, parsed["context"])
            if feedback:
                task.description += f"\n\nFeedback humano prioritario:\n{feedback}"
            output = run_step(product_owner.agent, task)
            decision, feedback = hitl_approve(label, output)
            if decision == "r":
                continue
            if decision == "n":
                steps[key] = {"status": "rejected", "output": output}
                _save_json(checkpoint_path, checkpoint)
                raise SystemExit(0)
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(output, encoding="utf-8")
            steps[key] = {"status": "approved", "output": output}
            _save_json(checkpoint_path, checkpoint)
            print(f"  Especificación aprobada: {feature['product_owner_spec_path']}")
            break

    _publish_plan_stories(features, project, checkpoint, checkpoint_path, plan_path.name)

def _dependency_section(spec_text: str) -> str:
    match = re.search(
        r"(?:^|\n)\s*#{0,3}\s*3\.\s*Dependencias con otras HUs\s*(.*?)(?=\n\s*#{0,3}\s*4\.|\Z)",
        spec_text, re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _related_features(feature: dict, all_features: list[dict]) -> list[dict]:
    current_spec = OUTPUT_DIR / _po_spec_relative_path(feature)
    if not current_spec.is_file():
        return []
    section = _dependency_section(current_spec.read_text(encoding="utf-8"))

    def mentions(source: str, target: dict) -> bool:
        title = str(target.get("title", ""))
        number = target.get("issue_number")
        references = [title, *re.findall(r"HU-[A-Za-z0-9-]+", title, re.IGNORECASE)]
        if number:
            references.append(f"#{number}")
        return any(reference and reference.casefold() in source.casefold() for reference in references)

    related = []
    for candidate in all_features:
        if candidate is feature or candidate.get("issue_number") == feature.get("issue_number"):
            continue
        candidate_spec = OUTPUT_DIR / _po_spec_relative_path(candidate)
        reverse_section = (
            _dependency_section(candidate_spec.read_text(encoding="utf-8"))
            if candidate_spec.is_file() else ""
        )
        if mentions(section, candidate) or mentions(reverse_section, feature):
            related.append(candidate)
    return related


def _architecture_context(feature: dict, all_features: list[dict]) -> tuple[str, str, list[dict]]:
    related = _related_features(feature, all_features)
    spec_parts = []
    for candidate in [feature, *related]:
        path = OUTPUT_DIR / _po_spec_relative_path(candidate)
        if path.is_file():
            spec_parts.append(f"### {candidate.get('title', '')}\n{_ctx_snippet(path.read_text(encoding='utf-8'))}")
    decision_parts = []
    for candidate in related:
        issue_number = candidate.get("issue_number")
        if not issue_number:
            continue
        try:
            comments = list_issue_comments(issue_number)
        except Exception as error:
            print(f"No se pudieron leer comentarios de #{issue_number}: {error}")
            continue
        marker = f"<!-- crewai-architecture:issue-{issue_number} -->"
        for comment in comments:
            if marker in comment.get("body", ""):
                decision_parts.append(
                    f"### Issue #{issue_number} — {candidate.get('title', '')}\n{comment['body']}"
                )
    return "\n\n".join(spec_parts), "\n\n".join(decision_parts), related


def _confirm_side_effect(prompt: str) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("s", "si", "sí", "y", "yes")


def _ask_workspace_permission(question: str) -> str:
    """Detiene al Developer hasta que la persona responda: s (una vez), a (siempre) o n (denegar)."""
    spinner = _ACTIVE_SPINNER
    if spinner:
        spinner.pause()
    try:
        print(f"\n🔐 PERMISO REQUERIDO — {question}")
        print("   [s] permitir esta vez   [a] permitir siempre durante esta ejecución   [n] denegar")
        while True:
            _flush_input_buffer()
            try:
                answer = input("👉 Tu respuesta [s/a/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "n"
            if answer in ("s", "a", "n"):
                return answer
            print("  Opción inválida. Usa s, a o n.")
    finally:
        if spinner:
            spinner.resume()


def _publish_architecture_comment(feature: dict, output: str) -> bool:
    issue_number = feature.get("issue_number")
    if not issue_number:
        print("La HU no tiene número de Issue; el análisis queda solo en el workspace local.")
        return False
    title = feature.get("title", "")
    marker = f"<!-- crewai-architecture:issue-{issue_number} -->"
    body = f"{marker}\n## Análisis de Arquitectura aprobado\n\nHU: **{title}**\n\n{output}"
    if not _confirm_side_effect(f"¿Publicar el análisis aprobado como comentario en la Issue #{issue_number}? [s/n]: "):
        print("Comentario no publicado; el análisis quedó guardado localmente.")
        return False
    try:
        create_issue_comment(issue_number, body)
    except Exception as error:
        print(f"No se pudo publicar el comentario de Arquitectura: {error}")
        return False
    print(f"Análisis publicado como comentario en la Issue #{issue_number}.")
    return True


def _development_task(key: str, feature: dict, workspace: Path, project_context: str,
                      architecture_context: str, prior_decisions: str, approved_outputs: dict):
    if key == "architect":
        task = architect.build_task(feature)
        task.description += (
            "\n\nInventario y código relevante del repositorio:\n" + project_context
            + "\n\n"
            "\n\nEspecificaciones PO de esta HU y HUs relacionadas:\n" + (architecture_context or "(no disponibles)")
            + "\n\nComentarios de Arquitectura aprobados en HUs relacionadas:\n"
            + (prior_decisions or "(no hay decisiones previas publicadas)")
        )
        return task
    if key == "developer":
        approved_architecture = str(approved_outputs.get("architect", ""))
        complete_architecture = (
            architecture_context + "\n\nAnálisis aprobado por Arquitectura:\n" + approved_architecture
        )
        return developer.build_task(
            feature, str(workspace), project_context, complete_architecture, prior_decisions,
        )
    task = testing.build_task(feature, str(workspace)) if key == "testing" else security.build_task(feature)
    task.description += (
        f"\n\nWorkspace de trabajo: {workspace}\n"
        "Inventario y código relevante del repositorio:\n" + project_context
        + "\n\nContrato aprobado por Arquitectura:\n" + _ctx_snippet(approved_outputs.get("architect", ""))
        + "\n\nCambios propuestos por Developer:\n" + _ctx_snippet(approved_outputs.get("developer", ""))
    )
    return task


def run_development_flow(feature: dict, all_features: list[dict]) -> None:
    """Ejecuta Arquitectura, Full Stack, Testing y Seguridad con aprobación por etapa."""
    repo = devops.feature_repo()
    base_branch = devops.feature_base_branch()
    workspace = devops.prepare_workspace(feature, OUTPUT_DIR / "workspaces", repo, base_branch)
    access = developer.attach_workspace(workspace, _ask_workspace_permission)
    run_dir = OUTPUT_DIR / "development" / f"issue-{_feature_key(feature)}-{_feature_slug(feature)}"
    checkpoint_path = run_dir / ".checkpoint.json"
    checkpoint = _load_json(checkpoint_path, {"steps": {}})
    previous_issue = checkpoint.get("issue_number")
    if previous_issue and previous_issue != feature.get("issue_number"):
        raise SystemExit("El checkpoint de desarrollo pertenece a otra Issue.")
    if checkpoint.get("pull_request"):
        print(f"Esta HU ya tiene un PR creado: {checkpoint['pull_request']}")
        return
    checkpoint["issue_number"] = feature.get("issue_number")
    checkpoint["workspace"] = str(workspace)
    steps_state = checkpoint.setdefault("steps", {})
    approved_outputs = {
        key: value.get("output", "") for key, value in steps_state.items()
        if value.get("status") == "approved"
    }
    changed_files = set(checkpoint.get("changed_files", []))

    architecture_context, prior_decisions, related = _architecture_context(feature, all_features)
    project_context = devops.workspace_context(workspace)
    steps = (
        ("architect", "Arquitecto de Soluciones", architect.agent, "user_story.md", False),
        ("developer", "Developer Full Stack", developer.agent, "developer_spec.md", True),
        ("testing", "Ingeniero de pruebas", testing.agent, "testing_report.md", True),
        ("security", "Revisor de seguridad", security.agent, "security_report.md", False),
    )
    print(f"\nDesarrollo: #{feature.get('issue_number', '?')} {feature.get('title', '')}")
    print(f"Repositorio: {repo} | Rama: {devops.feature_branch(feature)} | Base PR: {base_branch}")
    if related:
        print("HUs relacionadas detectadas: " + ", ".join(
            f"#{item.get('issue_number')} {item.get('title')}" for item in related
        ))

    for key, label, agent, spec_file, extracts_code in steps:
        step = steps_state.get(key, {})
        if step.get("status") == "approved":
            print(f"Aprobado previamente: {label}")
            if key == "architect" and not step.get("comment_published"):
                step["comment_published"] = _publish_architecture_comment(feature, step.get("output", ""))
                _save_json(checkpoint_path, checkpoint)
            continue

        feedback = ""
        while True:
            task = _development_task(
                key, feature, workspace, project_context, architecture_context,
                prior_decisions, approved_outputs,
            )
            if feedback:
                task.description += f"\n\nFeedback humano prioritario:\n{feedback}"
            output = run_step(agent, task)
            decision, feedback = hitl_approve(label, output)
            if decision == "r":
                continue
            if decision == "n":
                steps_state[key] = {"status": "rejected", "output": output}
                checkpoint["changed_files"] = sorted(changed_files)
                _save_json(checkpoint_path, checkpoint)
                raise SystemExit(0)

            spec_path = run_dir / "specs" / spec_file
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(output, encoding="utf-8")
            if extracts_code:
                devops.apply_workspace_changes(output, workspace)
                changed_files = set(devops.workspace_changes(workspace))
                project_context = devops.workspace_context(workspace)
            if key == "developer":
                checkpoint["developer_permissions"] = list(access.audit)
                for line in access.audit:
                    print(f"  [Developer] {line}")
            approved_outputs[key] = output
            steps_state[key] = {"status": "approved", "output": output}
            if key == "architect":
                steps_state[key]["comment_published"] = _publish_architecture_comment(feature, output)
            checkpoint["changed_files"] = sorted(changed_files)
            _save_json(checkpoint_path, checkpoint)
            break

    changed_files = set(devops.workspace_changes(workspace))
    if not changed_files:
        print("Las etapas fueron aprobadas, pero no se generaron archivos modificados; no se puede crear un PR.")
        return
    print("\nTodas las etapas fueron aprobadas.")
    print("Archivos para el PR: " + ", ".join(sorted(changed_files)))
    if not _confirm_side_effect(
        f"¿Estás conforme con el resultado y autorizas crear el PR de {repo}:{devops.feature_branch(feature)} "
        f"hacia {base_branch}? [s/n]: "
    ):
        print("Creación del PR cancelada. El workspace y la rama local se conservaron.")
        return
    try:
        pr_url = devops.create_feature_pr(
            workspace, feature, sorted(changed_files), repo, base_branch,
        )
    except Exception as error:
        print(f"No se pudo crear el PR: {error}")
        return
    checkpoint["pull_request"] = pr_url
    _save_json(checkpoint_path, checkpoint)
    print(f"PR creado: {pr_url}")


def main() -> None:
    print("\nCrewAI — selector de flujo")
    print("  1. Product Owner: leer el plan, generar specs y publicarlas como Issues del proyecto")
    print("  2. Desarrollo Full Stack: seleccionar una Issue y preparar un PR")
    try:
        mode = input("Selecciona flujo [1/2]: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(0)
    if mode not in ("1", "2"):
        print("Opción inválida.")
        return

    print("\n[MCP Proyectos] Autenticando...")
    proj_tools()
    project = _select_project(list_projects())
    print(f"Proyecto: {project.get('title', '(sin título)')}")

    if mode == "1":
        run_product_owner_from_plan(project)
        return

    features = list_project_features(project["id"])
    available = [feature for feature in features if str(feature.get("state", "open")).casefold() != "closed"]
    if not available:
        print("El proyecto no tiene Issues abiertas disponibles.")
        return
    print("\nIssues disponibles:")
    _print_features(available)
    selected = _select_item(available, f"Selecciona Issue [1-{len(available)}]: ")
    run_development_flow(selected, features)


if __name__ == "__main__":
    main()
