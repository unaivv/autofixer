"""Run commands inside a single Node Docker image with the repo bind-mounted."""

from __future__ import annotations

from typing import Tuple

import docker
import docker.errors
from docker.errors import DockerException
from loguru import logger

from config import Settings


def run_in_docker(settings: Settings, repo_path: str, bash_script: str) -> Tuple[bool, str]:
    """Execute bash -lc script with cwd=/workspace. Returns (ok, combined_logs)."""
    try:
        client = docker.from_env()
    except DockerException as e:
        logger.error("Docker not available: {}", e)
        return False, str(e)

    image = settings.docker_node_image
    try:
        out = client.containers.run(
            image,
            command=["bash", "-lc", bash_script],
            remove=True,
            volumes={repo_path: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            stdout=True,
            stderr=True,
        )
        text = out.decode("utf-8", errors="replace") if isinstance(out, (bytes, bytearray)) else str(out)
        return True, text
    except docker.errors.ContainerError as e:
        # docker-py only sets .stderr (bytes or None); there is no .stdout.
        raw = e.stderr
        if raw is None:
            err_text = ""
        elif isinstance(raw, (bytes, bytearray)):
            err_text = raw.decode("utf-8", errors="replace")
        else:
            err_text = str(raw)
        msg = f"{err_text}\nexit={e.exit_status}"
        return False, msg
    except Exception as e:
        logger.exception("docker run failed")
        return False, str(e)
