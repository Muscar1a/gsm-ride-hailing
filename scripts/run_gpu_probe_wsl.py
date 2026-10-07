"""Launch the isolated Week 2 GPU probe under WSL; timeout is 30 minutes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    workspace = Path(__file__).resolve().parents[1]
    probe_root = workspace / ".cache/gpu_probe_19001"
    if os.name != "posix":
        raise RuntimeError("Run this launcher with Python inside WSL Ubuntu")
    python_path = probe_root / "venv/bin/python"
    site_packages = probe_root / "venv/lib/python3.11/site-packages"
    probe_env = os.environ.copy()
    library_paths = [str(path) for path in (site_packages / "nvidia").glob("*/lib")]
    library_paths += ["/usr/lib/wsl/lib"]
    probe_env["LD_LIBRARY_PATH"] = ":".join(library_paths)
    probe_env["CUDA_PATH"] = str(site_packages / "nvidia/cuda_runtime")
    probe_env["NUMBA_CUDA_DRIVER"] = "/usr/lib/wsl/lib/libcuda.so.1"
    for variable_name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        probe_env[variable_name] = "1"
    command = [str(python_path), str(workspace / "scripts/probe_week2_gpu.py")]
    command += ["--snapshot", str(workspace / ".cache/week2-evaluation-574cf501-20261007")]
    command += argv if argv is not None else sys.argv[1:]
    result = subprocess.run(command, env=probe_env, cwd=workspace, timeout=1800)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
