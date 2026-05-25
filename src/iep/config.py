import os
from pathlib import Path

# Root of the project (two levels up from this file: src/iep/config.py → project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directory where IFC files land after SFTP transfer.
IFC_DIR: Path = PROJECT_ROOT / "data"

# Vercel's deployment filesystem is read-only; /tmp is the only writable location.
_on_vercel = os.environ.get("VERCEL") == "1"
RESULTS_DIR: Path = Path("/tmp/iep-results") if _on_vercel else PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
