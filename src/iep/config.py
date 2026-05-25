from pathlib import Path

# Root of the project (two levels up from this file: src/iep/config.py → project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directory where IFC files land after SFTP transfer.
IFC_DIR: Path = PROJECT_ROOT / "data"

# Directory where processing results are cached as {application_ref}.json
RESULTS_DIR: Path = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
