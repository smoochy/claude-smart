"""PostToolUse hook — record the tool invocation and its outcome.

For Claude Code, this hook only appends ``Assistant_tool`` records to the
session buffer; the ``Stop`` and ``SessionEnd`` hooks own publishing. Codex
exec (non-interactive `codex exec --json`) never fires ``Stop`` or any
session-end-like event, so without an additional flush every codex run
leaves its turns in the local JSONL buffer and the reflexio backend never
sees them. To close that gap we opportunistically publish from
PostToolUse when the host is Codex — see ``_maybe_flush_codex`` below.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from claude_smart import ids, publish, runtime, state

_LOGGER = logging.getLogger(__name__)

# Tool inputs are persisted locally and later published to reflexio, so we
# apply a conservative redaction pass at ingestion time. Chosen to avoid
# false positives over maximal coverage — the dashboard shows these
# verbatim, and users noticing a masked command is far less surprising
# than a masked `LOG_LEVEL=INFO`.
_MAX_STR_LEN = 4096
_SECRET_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Z][A-Z0-9_]{2,})=(?P<quote>['\"]?)"
    r"(?P<value>[A-Za-z0-9+/=_\-]{20,})(?P=quote)"
)


def _looks_like_secret(value: str) -> bool:
    """Heuristic: mixed-case letters plus digits suggest a high-entropy token."""
    has_lower = any(c.islower() for c in value)
    has_upper = any(c.isupper() for c in value)
    has_digit = any(c.isdigit() for c in value)
    return has_lower and has_upper and has_digit


def _mask_secrets(text: str) -> str:
    def sub(match: "re.Match[str]") -> str:
        value = match.group("value")
        if not _looks_like_secret(value):
            return match.group(0)
        key = match.group("key")
        quote = match.group("quote")
        return f"{key}={quote}<redacted:{len(value)}>{quote}"

    return _SECRET_ASSIGNMENT.sub(sub, text)


def _redact_string(value: str) -> str:
    masked = _mask_secrets(value)
    if len(masked) > _MAX_STR_LEN:
        return masked[:_MAX_STR_LEN] + "…(truncated)"
    return masked


def _redact(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Redact obvious secrets and truncate oversized string values.

    Only top-level string values are inspected — nested dicts/lists and
    non-string scalars pass through unchanged. Claude Code tool payloads
    are flat in practice (Bash.command, Edit.file_path, etc.), so deeper
    recursion isn't worth the false-positive surface.

    Args:
        tool_input (dict[str, Any]): Raw ``tool_input`` from the PostToolUse
            payload.

    Returns:
        dict[str, Any]: New dict with redaction applied.
    """
    return {
        k: _redact_string(v) if isinstance(v, str) else v for k, v in tool_input.items()
    }


def _derive_status(tool_response: Any) -> str:
    """Classify the tool outcome as 'success' or 'error'.

    Claude Code's PostToolUse payload puts the tool response under
    ``tool_response``, which may be a dict (with an ``is_error`` / ``error``
    field) or a bare string. Unknown shapes default to success.
    """
    if isinstance(tool_response, dict):
        if tool_response.get("is_error") or tool_response.get("error"):
            return "error"
    return "success"


_OUTPUT_TEXT_KEYS = ("stdout", "stderr", "output", "content", "text", "error")


def _flatten_tool_response_text(tool_response: Any) -> str:
    """Flatten ``tool_response`` into a single string for buffering.

    Claude Code delivers tool responses in heterogeneous shapes — Bash sends
    a dict with ``stdout``/``stderr``, Edit/Read send a string or a dict
    with ``content``/``output``, and failures populate ``error``. Joining
    the well-known string-valued keys preserves the parts most useful for
    downstream learning (failure messages, command output) without
    serializing entire structured payloads.

    Note: structured ``content`` lists (e.g. ``[{type: 'text', text: ...}]``)
    are not flattened — only top-level string values are joined. If a tool
    starts emitting block-form content we want to capture, add a dedicated
    branch here.

    Args:
        tool_response (Any): The raw ``tool_response`` from the PostToolUse
            payload.

    Returns:
        str: A flattened string. Empty when no textual content is present.
    """
    if tool_response is None:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        parts = [
            tool_response[key]
            for key in _OUTPUT_TEXT_KEYS
            if isinstance(tool_response.get(key), str) and tool_response[key]
        ]
        if parts:
            return "\n".join(parts)
        for key in ("text", "content"):
            value = tool_response.get(key)
            if isinstance(value, str):
                return value
        return ""
    for attr in ("text", "content"):
        value = getattr(tool_response, attr, None)
        if isinstance(value, str):
            return value
    return ""


_CODEX_SYNTHETIC_ASSISTANT_TEXT = (
    "<codex turn in progress — synthesised anchor for incremental publish>"
)


def _maybe_flush_codex(*, session_id: str, payload: dict[str, Any]) -> None:
    """Synthesise an Assistant anchor and publish unpublished turns under Codex.

    Codex's non-interactive ``codex exec --json`` mode never fires a Stop or
    SessionEnd hook (only SessionStart, UserPromptSubmit, and PostToolUse),
    so without this opportunistic flush the buffered User + Assistant_tool
    records never reach the reflexio backend. ``state.unpublished_slice``
    folds tool records into the *next* Assistant turn's ``tools_used``;
    appending a synthetic Assistant before each publish keeps tools from
    being silently dropped at publish time.

    The synthetic anchor uses a distinctive marker string so a future audit
    can grep for it; the first publish carries the User turn + every
    buffered tool, and later publishes carry only the new tool fired since
    the previous flush.

    Failures are absorbed (logged at debug) — the hook must never break the
    Codex session even when reflexio is unreachable.

    Args:
        session_id (str): Codex thread id from the hook payload.
        payload (dict[str, Any]): Raw PostToolUse hook payload, used to
            derive the per-project ``user_id`` from ``cwd``.

    Returns:
        None
    """
    # Use whichever resolver this build of claude_smart exposes — older
    # 0.2.31 packages (the marketplace baseline) called it
    # ``resolve_project_id`` while 0.2.39+ renames it to ``resolve_user_id``.
    # ``getattr`` keeps the fix portable across both shapes so the same
    # source file can be copied into either cache slot.
    resolver = getattr(ids, "resolve_user_id", None) or ids.resolve_project_id
    project_id = resolver(payload.get("cwd"))
    state.append(
        session_id,
        {
            "ts": int(time.time()),
            "role": "Assistant",
            "content": _CODEX_SYNTHETIC_ASSISTANT_TEXT,
            "user_id": project_id,
            "synthesised_by": "codex_post_tool_anchor",
        },
    )
    try:
        publish.publish_unpublished(
            session_id=session_id,
            project_id=project_id,
            force_extraction=False,
            skip_aggregation=False,
        )
    except Exception as exc:  # noqa: BLE001 — hook must never break the session.
        _LOGGER.debug("codex post_tool publish failed: %s", exc)


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name") or ""
    if not session_id or not tool_name:
        return

    tool_response = payload.get("tool_response")
    output_text = _flatten_tool_response_text(tool_response)
    record = {
        "ts": int(time.time()),
        "role": "Assistant_tool",
        "tool_name": tool_name,
        "tool_input": _redact(payload.get("tool_input") or {}),
        "tool_output": _redact_string(output_text) if output_text else "",
        "status": _derive_status(tool_response),
    }
    state.append(session_id, record)

    if runtime.is_codex():
        _maybe_flush_codex(session_id=session_id, payload=payload)
