"""Run from a source checkout without installing dependencies or changing system settings."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from affinityqa.cli import main

raise SystemExit(main())

