"""Install the GPU probe into workspace-owned directories only."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
import urllib.request
from pathlib import Path


def main() -> None:
    workspace = Path(__file__).resolve().parents[1]
    probe_root = workspace / ".cache/gpu_probe_19001"
    if os.name != "posix":
        raise RuntimeError("Run this installer with Python inside WSL Ubuntu")
    uv_path = probe_root / "tools/uv"
    uv_path.parent.mkdir(parents=True, exist_ok=True)
    uv_version = "0.10.12"
    uv_url = (
        f"https://github.com/astral-sh/uv/releases/download/{uv_version}/"
        "uv-x86_64-unknown-linux-gnu.tar.gz"
    )
    if not uv_path.exists():
        print("Downloading the isolated uv executable", flush=True)
        with urllib.request.urlopen(uv_url, timeout=60) as response:
            archive_bytes = response.read(100_000_001)
        if len(archive_bytes) > 100_000_000:
            raise ValueError("uv archive exceeds the bounded download size")
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            executable = archive.extractfile("uv-x86_64-unknown-linux-gnu/uv")
            if executable is None:
                raise ValueError("uv executable is missing from the official archive")
            uv_path.write_bytes(executable.read())
        uv_path.chmod(0o755)
        (probe_root / "uv_source.json").write_text(
            json.dumps(
                {
                    "version": uv_version,
                    "url": uv_url,
                    "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    install_env = os.environ.copy()
    install_env.update(
        UV_PYTHON_INSTALL_DIR=str(probe_root / "python"),
        UV_PYTHON_BIN_DIR=str(probe_root / "bin"),
        UV_CACHE_DIR=str(probe_root / "uv_cache"),
        UV_HTTP_TIMEOUT="60",
        UV_PYTHON_PREFERENCE="only-managed",
    )
    python_path = probe_root / "venv/bin/python"
    if not python_path.exists():
        subprocess.run(
            [str(uv_path), "python", "install", "3.11.15"],
            env=install_env,
            check=True,
            timeout=300,
        )
        subprocess.run(
            [str(uv_path), "venv", "--python", "3.11.15", str(probe_root / "venv")],
            env=install_env,
            check=True,
            timeout=120,
        )
    subprocess.run(
        [
            str(uv_path),
            "pip",
            "install",
            "--python",
            str(python_path),
            "--extra-index-url",
            "https://pypi.nvidia.com",
            "-r",
            str(workspace / "scripts/gpu_probe_requirements.txt"),
            "-c",
            str(workspace / "scripts/gpu_probe_constraints.txt"),
        ],
        env=install_env,
        check=True,
        timeout=1200,
    )
    freeze_result = subprocess.run(
        [str(uv_path), "pip", "freeze", "--python", str(python_path)],
        env=install_env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    (probe_root / "resolved_requirements.txt").write_text(freeze_result.stdout, encoding="utf-8")
    print(f"GPU probe environment ready: {python_path}", flush=True)


if __name__ == "__main__":
    main()
