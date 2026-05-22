"""Resolve stable identifiers for Claude Code sessions.

Two identifiers matter to reflexio:

- ``session_id``: Claude Code's per-session id, passed in hook stdin. We
  forward it to reflexio's interaction ``session_id`` field so individual
  turns remain attributable to their conversation, but it is no longer
  the scope key for extracted preferences.
- ``project_id``: a stable, cross-session name for the project. We use
  this as reflexio's ``user_id`` for preferences, so user preferences
  extracted in one session are visible to every later session in the
  same repo. ``agent_version`` is hardcoded to ``"claude-code"`` in the
  adapter so shared skills roll up globally across all projects rather than
  per project.
"""

from __future__ import annotations

import logging
import os
import subprocess  # noqa: S404 — git invocation with a fixed flag set.
import uuid
from pathlib import Path

from claude_smart import env_config

_LOGGER = logging.getLogger(__name__)


def resolve_project_id(cwd: str | os.PathLike[str] | None = None) -> str:
    """Return a stable project identifier for the given working directory.

    Managed Reflexio installs are user-scoped instead of project-scoped:
    when ``REFLEXIO_API_KEY`` is configured, the persisted
    ``REFLEXIO_USER_ID`` UUID is returned. Local installs without an API key
    keep using the git/project name.

    Prefers the basename of the git toplevel (so worktrees, submodules, and
    `cd src/` all still map to the same project). Falls back to the cwd
    basename when the directory is not inside a git repo.

    Args:
        cwd: Working directory to resolve. Defaults to ``os.getcwd()``.

    Returns:
        str: A non-empty identifier. Never raises.
    """
    managed_user_id = _managed_user_id()
    if managed_user_id:
        return managed_user_id

    base = Path(cwd) if cwd is not None else Path.cwd()
    try:
        result = subprocess.run(  # noqa: S603, S607 — fixed argv, cwd is a Path.
            ["git", "rev-parse", "--show-toplevel"],
            cwd=base,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            toplevel = result.stdout.strip()
            if toplevel:
                return Path(toplevel).name
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _LOGGER.debug("git toplevel resolution failed: %s", exc)
    return base.name or "unknown-project"


def _managed_user_id() -> str:
    env_config.load_reflexio_env()
    if not os.environ.get(env_config.REFLEXIO_API_KEY_ENV):
        return ""
    user_id = os.environ.get(env_config.REFLEXIO_USER_ID_ENV, "").strip()
    if user_id:
        return user_id

    user_id = str(uuid.uuid4())
    try:
        env_config.set_env_vars(
            env_config.REFLEXIO_ENV_PATH,
            {env_config.REFLEXIO_USER_ID_ENV: user_id},
        )
    except OSError as exc:
        _LOGGER.debug("could not persist managed Reflexio user id: %s", exc)
    os.environ[env_config.REFLEXIO_USER_ID_ENV] = user_id
    return user_id
