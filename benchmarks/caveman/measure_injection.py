"""Channel 1 + 2b: claude-smart injection token weight, normal vs compact renderer.

Measured (real reflexio.db state) + projected (synthetic playbooks/profiles at
N in {5,20,50}) through the REAL context_format renderers. tiktoken cl100k_base.

Run: uv run --with tiktoken python benchmarks/caveman/measure_injection.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Make the plugin package importable without installing it.
_THIS_DIR = Path(__file__).resolve().parent
_PLUGIN_SRC = _THIS_DIR.parents[1] / "plugin" / "src"
sys.path.insert(0, str(_PLUGIN_SRC))

import tiktoken  # noqa: E402
from claude_smart import context_format  # noqa: E402

ENC = tiktoken.get_encoding("cl100k_base")
DB = Path.home() / ".reflexio" / "data" / "reflexio.db"

# Defaults matching what ships (citations on, markdown links). Pin explicitly so
# the numbers are reproducible regardless of the caller's environment.
os.environ.setdefault("CLAUDE_SMART_CITATIONS", "on")
os.environ.setdefault("CLAUDE_SMART_CITATION_LINK_STYLE", "markdown")
os.environ.pop("REFLEXIO_URL", None)  # keep dashboard URLs local/deterministic


def ntok(s: str) -> int:
    return len(ENC.encode(s))


def render_pair(user_pb, agent_pb, profiles) -> tuple[str, str]:
    normal, _ = context_format.render_inline_with_registry(
        project_id="proj", user_playbooks=user_pb,
        agent_playbooks=agent_pb, profiles=profiles,
    )
    compact, _ = context_format.render_inline_compact_with_registry(
        project_id="proj", user_playbooks=user_pb,
        agent_playbooks=agent_pb, profiles=profiles,
    )
    return normal, compact


def measured_now() -> None:
    print("== Channel 1a: MEASURED (real reflexio.db) ==")
    if not DB.exists():
        print("  no reflexio.db — skipping")
        return
    uri = f"file:{DB}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    def rows(table, cols):
        try:
            return [dict(r) for r in con.execute(f"select {cols} from {table}")]
        except sqlite3.Error as exc:
            print(f"  {table}: read error {exc}")
            return []

    # Column names are best-effort; fall back to * if the schema differs.
    def safe(table):
        try:
            return [dict(r) for r in con.execute(f"select * from {table}")]
        except sqlite3.Error:
            return []

    user_pb = safe("user_playbooks")
    agent_pb = safe("agent_playbooks")
    profiles = safe("profiles")
    con.close()
    print(f"  rows: user_playbooks={len(user_pb)} "
          f"agent_playbooks={len(agent_pb)} profiles={len(profiles)}")
    normal, compact = render_pair(user_pb, agent_pb, profiles)
    print(f"  normal={ntok(normal)} tok  compact={ntok(compact)} tok")
    if not normal and not compact:
        print("  -> injection footprint is EMPTY at current state (0 learned items)")


def synth_playbook(i: int) -> dict:
    return {
        "user_playbook_id": f"u{i}",
        "content": (
            f"When editing stack file {i} under stacks/, patch only the local "
            "repo and let the Komodo webhook redeploy; never scp to the host."
        ),
        "trigger": f"a compose.yaml or .env under stacks/app{i} changes",
        "rationale": (
            "remote edits bypass the git-push deploy chain and cause drift "
            "between the repo and the running stack"
        ),
    }


def synth_profile(i: int) -> dict:
    return {
        "profile_id": f"p{i}",
        "content": (
            f"Prefer terse, fragment-style output in project context {i}; "
            "drop articles and filler, keep code and error strings verbatim."
        ),
    }


def projected() -> None:
    print("\n== Channel 1b: PROJECTED (synthetic, real renderer) ==")
    print(f"{'N':>4} {'normal':>8} {'compact':>8} {'delta':>7} {'saved%':>7}")
    for n in (5, 20, 50):
        # split N across skills + preferences roughly 60/40, like real vaults
        n_pb = round(n * 0.6)
        n_pf = n - n_pb
        user_pb = [synth_playbook(i) for i in range(n_pb)]
        profiles = [synth_profile(i) for i in range(n_pf)]
        normal, compact = render_pair(user_pb, [], profiles)
        tn, tc = ntok(normal), ntok(compact)
        pct = 100 * (tn - tc) / tn if tn else 0.0
        print(f"{n:>4} {tn:>8} {tc:>8} {tn - tc:>7} {pct:>6.1f}%")


if __name__ == "__main__":
    measured_now()
    projected()
