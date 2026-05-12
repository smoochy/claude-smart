"""SessionStart hook — apply startup defaults without broad memory retrieval."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from claude_smart import hook
from claude_smart.reflexio_adapter import Adapter

# Claude-smart's preferred extraction cadence — more frequent, smaller windows
# than reflexio's out-of-box 10/5. Applied idempotently to the reflexio server
# on every SessionStart via Adapter.apply_extraction_defaults.
_CLAUDE_SMART_WINDOW_SIZE = 5
_CLAUDE_SMART_STRIDE_SIZE = 3
# Optimizer is on by default. Set this env var to "0" to skip pushing the
# claude-smart optimizer defaults on SessionStart (kill switch).
_DISABLE_OPTIMIZER_ENV = "CLAUDE_SMART_ENABLE_OPTIMIZER"
_OPTIMIZER_TIMEOUT_SECONDS = 300


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    if not session_id:
        hook.emit_continue()
        return

    adapter = Adapter()
    adapter.apply_extraction_defaults(
        window_size=_CLAUDE_SMART_WINDOW_SIZE,
        stride_size=_CLAUDE_SMART_STRIDE_SIZE,
    )
    if os.environ.get(_DISABLE_OPTIMIZER_ENV) != "0":
        adapter.apply_optimizer_defaults(
            script_path=_optimizer_assistant_path(),
            timeout_seconds=_OPTIMIZER_TIMEOUT_SECONDS,
        )
    hook.emit_continue()


def _optimizer_assistant_path() -> str:
    executable = Path(sys.executable)
    suffix = ".exe" if os.name == "nt" else ""
    return str(executable.with_name(f"claude-smart-optimizer-assistant{suffix}"))
