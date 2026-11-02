import sys
from pathlib import Path

CANDIDATE = Path(__file__).resolve().parent.parent
DEV = CANDIDATE / "tests" / "fixtures" / "dev6"
if str(CANDIDATE) not in sys.path:
    sys.path.insert(0, str(CANDIDATE))
