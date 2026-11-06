"""Run the pipeline checks without Copilot, MCP or GitHub credentials."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"
os.environ["OTEL_SDK_DISABLED"] = "true"
for command in [["-m", "unittest", "discover", "-s", "tests", "-v"]]:
    subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
print("All pipeline checks passed. No model or external service was called.")
