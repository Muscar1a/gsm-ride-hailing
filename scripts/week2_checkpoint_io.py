"""Run the frozen evaluator with bounded retries for Windows checkpoint sharing."""

from __future__ import annotations

import contextlib
import os
import runpy
import sys
import time
import uuid
from pathlib import Path

REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6)


def replace_with_retry(temporary: Path, path: Path) -> None:
    for attempt in range(len(REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(temporary, path)
        except PermissionError as exc:
            if (
                sys.platform != "win32"
                or getattr(exc, "winerror", None) not in (5, 32, 33)
                or attempt == len(REPLACE_RETRY_DELAYS)
            ):
                raise
            print(
                f"checkpoint-io: retry {attempt + 1} replacing {path.name}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(REPLACE_RETRY_DELAYS[attempt])
        else:
            return


@contextlib.contextmanager
def atomic_path_with_retry(path: Path):
    """Keep the original atomic-write contract and retry only the replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        yield temporary
        replace_with_retry(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_checkpoint_io() -> None:
    from gsm_poc import artifacts

    # Runtime I/O only: no frozen source, config, estimator or result bytes change.
    artifacts.atomic_path = atomic_path_with_retry


def main() -> None:
    install_checkpoint_io()
    runpy.run_module("gsm_poc", run_name="__main__")


if __name__ == "__main__":
    main()
