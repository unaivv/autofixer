"""Run commands inside a single Node Docker image with the repo bind-mounted."""

from __future__ import annotations

import sys
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
    logger.info(
        "Docker: starting image={} (repo -> /workspace). Streaming logs below. "
        "Silence can mean: pulling the image, npm/pnpm resolve, or turbo starting — often several minutes.",
        image,
    )

    container = None
    try:
        container = client.containers.create(
            image,
            command=["bash", "-lc", bash_script],
            volumes={repo_path: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
        )
        collected: list[bytes] = []
        container.start()
        try:
            for chunk in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                if not chunk:
                    continue
                collected.append(chunk)
                try:
                    piece = (
                        chunk.decode("utf-8", errors="replace")
                        if isinstance(chunk, (bytes, bytearray))
                        else str(chunk)
                    )
                    sys.stdout.write(piece)
                    sys.stdout.flush()
                except OSError:
                    pass
        finally:
            wait_result = container.wait()
        status = wait_result.get("StatusCode", -1)
        text = b"".join(collected).decode("utf-8", errors="replace")
        ok = status == 0
        if ok:
            logger.info("Docker: finished OK (exit 0)")
            return True, text
        logger.error("Docker: container exited with status {}", status)
        return False, f"{text}\nexit={status}"
    except Exception as e:
        logger.exception("docker run failed")
        return False, str(e)
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                pass
            except Exception:
                pass
