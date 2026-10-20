"""Isolated entry point for a validated dashboard job."""

import sys
from pathlib import Path

from gsm_poc.ui.jobs import execute_job

if __name__ == "__main__":
    execute_job(Path(sys.argv[1]).resolve(), sys.argv[2])
