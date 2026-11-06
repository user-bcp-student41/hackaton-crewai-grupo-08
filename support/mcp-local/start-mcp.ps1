param(
    [string]$Owner = "user-bcp-student41",
    [string]$Repo  = "hackaton-grupo-08",
    [ValidateSet("auto", "podman", "docker")]
    [string]$Engine = "auto"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MCP GitHub Project Manager - Local HTTP Service" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# 1. Detect and validate container runtime (Podman / Docker)
# ------------------------------------------------------------
$hasPodman = [bool](Get-Command podman -ErrorAction SilentlyContinue)
$hasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)

$selectedEngine = $null

if ($Engine -eq "podman") {
    if (-not $hasPodman) { throw "Has especificado -Engine podman, pero 'podman' no esta en el PATH." }
    $selectedEngine = "podman"
} elseif ($Engine -eq "docker") {
    if (-not $hasDocker) { throw "Has especificado -Engine docker, pero 'docker' no esta en el PATH." }
    $selectedEngine = "docker"
} else {
    # Auto-detect: Prioriza Podman (entorno oficial del lab), fallback a Docker
    if ($hasPodman) {
        $selectedEngine = "podman"
    } elseif ($hasDocker) {
        $selectedEngine = "docker"
    } else {
        throw "No se encontro ni 'podman' ni 'docker' en el PATH. Instala Podman o Docker Desktop."
    }
}

Write-Host "Contenedores: Usando motor '$selectedEngine'" -ForegroundColor Green

# ------------------------------------------------------------
# 2. Validate GitHub CLI (gh) and obtain token
# ------------------------------------------------------------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) no esta disponible en el PATH. Ejecuta 'gh auth login' antes de iniciar."
}

Write-Host "Obteniendo token desde GitHub CLI..."
$token = gh auth token

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "No se pudo obtener el token con 'gh auth token'. Por favor inicia sesion con: gh auth login"
}

# ------------------------------------------------------------
# 3. Export environment variables consumed by compose.yaml
# ------------------------------------------------------------
$env:GITHUB_TOKEN = $token
$env:GITHUB_OWNER = $Owner
$env:GITHUB_REPO  = $Repo

Write-Host "  GITHUB_OWNER = $env:GITHUB_OWNER"
Write-Host "  GITHUB_REPO  = $env:GITHUB_REPO"
Write-Host "  GITHUB_TOKEN = [configurado correctamente]"
Write-Host ""

# ------------------------------------------------------------
# 4. Limpiar sesion anterior si existiera
# ------------------------------------------------------------
$sessionFile = Join-Path $PSScriptRoot ".mcp-session"
if (Test-Path $sessionFile) {
    Write-Host "Eliminando sesion MCP anterior..."
    Remove-Item $sessionFile -Force
    Write-Host ""
}

# ------------------------------------------------------------
# 5. Construir las imagenes
# ------------------------------------------------------------
Write-Host "Construyendo imagenes con $selectedEngine..." -ForegroundColor Yellow
Write-Host ""

Push-Location $PSScriptRoot
try {
    if ($selectedEngine -eq "podman") {
        podman build -f Dockerfile -t mcp-local_github-project .
        if ($LASTEXITCODE -ne 0) { throw "Fallo el build de github-project con Podman." }

        podman build -f Dockerfile -t mcp-local_github-task .
        if ($LASTEXITCODE -ne 0) { throw "Fallo el build de github-task con Podman." }
    } else {
        docker build -f Dockerfile -t mcp-local_github-project .
        if ($LASTEXITCODE -ne 0) { throw "Fallo el build de github-project con Docker." }

        docker build -f Dockerfile -t mcp-local_github-task .
        if ($LASTEXITCODE -ne 0) { throw "Fallo el build de github-task con Docker." }
    }
} finally {
    Pop-Location
}

# ------------------------------------------------------------
# 6. Start MCP HTTP service
# ------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Levantando MCP HTTP en puertos:" -ForegroundColor Cyan
Write-Host "  - GitHub Projects : http://localhost:8083" -ForegroundColor White
Write-Host "  - GitHub Tasks    : http://localhost:8081 (Usado por S1 y S2)" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($selectedEngine -eq "podman") {
    podman compose --in-pod false up
} else {
    docker compose up
}