"""Channels 2b + 3: caveman output savings and session-size context, from real
Claude Code transcripts.

Channel 3 (measured): split transcripts into caveman-active vs inactive by the
"CAVEMAN MODE ACTIVE" hook marker, compare assistant TEXT-block output tokens
per message (the prose caveman compresses — not thinking/tool_use).

Channel 2b (context): median session input size, as the denominator for the
projected injection share.

tiktoken cl100k_base. Read-only over ~/.claude/projects/**/*.jsonl.

Run: uv run --with tiktoken python benchmarks/caveman/measure_transcripts.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")
MARKER = "CAVEMAN MODE ACTIVE"
ROOT = Path.home() / ".claude" / "projects"


def ntok(s: str) -> int:
    return len(ENC.encode(s))


def text_tokens(content) -> int:
    """tiktoken count of assistant TEXT blocks only (skip thinking/tool_use)."""
    if not isinstance(content, list):
        return ntok(str(content)) if isinstance(content, str) else 0
    total = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            total += ntok(block.get("text", ""))
    return total


def analyze(path: Path):
    caveman = False
    msg_text_tokens: list[int] = []
    session_input_peak = 0
    for line in path.open(encoding="utf-8", errors="replace"):
        if MARKER in line:
            caveman = True
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        t = text_tokens(msg.get("content"))
        if t > 0:
            msg_text_tokens.append(t)
        usage = msg.get("usage") or {}
        ctx = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
        session_input_peak = max(session_input_peak, ctx)
    return caveman, msg_text_tokens, session_input_peak


def summarize(label: str, values: list[int]) -> None:
    if not values:
        print(f"  {label}: no data")
        return
    values.sort()
    print(f"  {label}: n_msgs={len(values)} "
          f"median={statistics.median(values):.0f} "
          f"mean={statistics.mean(values):.0f} "
          f"p90={values[int(len(values) * 0.9)]:.0f} tok/msg")


def main() -> None:
    files = list(ROOT.rglob("*.jsonl"))
    cave_tokens: list[int] = []
    plain_tokens: list[int] = []
    cave_sessions = plain_sessions = 0
    session_peaks: list[int] = []
    for f in files:
        try:
            caveman, toks, peak = analyze(f)
        except OSError:
            continue
        if peak:
            session_peaks.append(peak)
        if caveman:
            cave_sessions += 1
            cave_tokens.extend(toks)
        else:
            plain_sessions += 1
            plain_tokens.extend(toks)

    print(f"== Channel 3: MEASURED caveman output (transcripts={len(files)}) ==")
    print(f"  caveman-active sessions={cave_sessions}  inactive={plain_sessions}")
    summarize("caveman-active", cave_tokens)
    summarize("inactive      ", plain_tokens)
    if cave_tokens and plain_tokens:
        cm = statistics.median(cave_tokens)
        pm = statistics.median(plain_tokens)
        if pm:
            print(f"  median text-output reduction: "
                  f"{100 * (pm - cm) / pm:+.1f}%  ({pm:.0f} -> {cm:.0f} tok/msg)")

    print("\n== Channel 2b: session input-size context ==")
    if session_peaks:
        session_peaks.sort()
        med = statistics.median(session_peaks)
        print(f"  peak session input tokens: median={med:.0f} "
              f"p90={session_peaks[int(len(session_peaks) * 0.9)]:.0f} "
              f"(n={len(session_peaks)})")
        # Projected injection share using Channel 1b normal-render sizes.
        for n, inj in ((5, 693), (20, 1797), (50, 4005)):
            print(f"  injection@N={n} ({inj} tok) = "
                  f"{100 * inj / med:.1f}% of median session peak")


if __name__ == "__main__":
    main()
