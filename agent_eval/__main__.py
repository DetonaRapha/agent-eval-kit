"""Enable ``python -m agent_eval``."""

from __future__ import annotations

import sys

from agent_eval.cli import main

if __name__ == "__main__":
    sys.exit(main())
