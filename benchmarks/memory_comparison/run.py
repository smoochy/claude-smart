"""Benchmark orchestrator: replay → force extract → retrieve → judge → report.

Runs the 9 ground-truth scenarios against both ``claude-smart`` and
``claude-mem``, scores retrievals with an LLM judge, and writes a Markdown
report plus a raw JSON log under ``results/``.

Usage:
    uv run python -m benchmarks.memory_comparison.run              # full run
    uv run python -m benchmarks.memory_comparison.run --only ID    # single
    uv run python -m benchmarks.memory_comparison.run --dry-run    # no replay
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

INTER_SCENARIO_PAUSE_S = 4.0

_THIS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _THIS_DIR.parents[1]  # benchmarks/memory_comparison -> repo root
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from benchmarks.memory_comparison import replay as replay_mod  # noqa: E402
from benchmarks.memory_comparison.adapters import claude_mem as mem_adapter  # noqa: E402
from benchmarks.memory_comparison.adapters import claude_smart as smart_adapter  # noqa: E402
from benchmarks.memory_comparison.judge import JudgeScore, score  # noqa: E402
from benchmarks.memory_comparison.scenarios import SCENARIOS, Scenario  # noqa: E402

RESULTS_DIR = _THIS_DIR / "results"
LOG = logging.getLogger("membench")


@dataclass
class SystemResult:
    """One system's retrieval + judge outcome for a single scenario."""

    system: str
    retrieved: list[str]
    score: JudgeScore
    notes: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """Per-scenario record combining replay metadata and both systems' scores."""

    scenario_id: str
    category: str
    ground_truth: str
    probe_query: str
    project_dir: str
    session_id: str
    replay_ok: bool
    replay_error: str | None
    systems: list[SystemResult]


def _run_scenario(scenario: Scenario, *, dry_run: bool) -> ScenarioResult:
    """Execute one scenario end-to-end and collect both systems' scores.

    Args:
        scenario (Scenario): Ground-truth case to run.
        dry_run (bool): If True, skip ``claude -p`` replay and just query
            whatever is already in the two stores. Useful for harness smoke
            tests.

    Returns:
        ScenarioResult: All rows the reporter needs.
    """
    project_dir = replay_mod.scratch_dir_for(scenario.id)
    session_id = ""
    replay_ok = True
    replay_error: str | None = None
    smart_notes: list[str] = []
    mem_notes: list[str] = []

    if dry_run:
        LOG.info("[%s] dry-run: skipping replay", scenario.id)
    else:
        LOG.info(
            "[%s] injecting %d turns into both systems",
            scenario.id,
            len(scenario.turns),
        )
        result = replay_mod.replay_scenario(
            scenario_id=scenario.id, turns=scenario.turns
        )
        project_dir = result.project_dir
        session_id = result.session_id
        replay_ok = result.smart_ok or result.mem_ok
        replay_error = "; ".join(result.errors) if result.errors else None
        if not result.smart_ok:
            smart_notes.append("injection failed; see replay errors")
        if not result.mem_ok:
            mem_notes.append("injection failed; see replay errors")

        LOG.info(
            "[%s] waiting for claude-smart extraction (non-blocking publish)",
            scenario.id,
        )
        if not smart_adapter.wait_for_extraction(
            project_dir=project_dir, session_id=session_id, timeout_s=150.0
        ):
            smart_notes.append("extraction timeout; scores may understate")
        LOG.info("[%s] waiting for claude-mem worker to drain", scenario.id)
        if not mem_adapter.wait_for_worker_drain(
            session_id=session_id,
            project=str(project_dir),
            timeout_s=180.0,
        ):
            mem_notes.append("worker drain timeout; scores may understate")

    smart_hits = smart_adapter.retrieve(
        project_dir=project_dir,
        session_id=session_id,
        probe_query=scenario.probe_query,
    )
    mem_hits = mem_adapter.retrieve(
        project=str(project_dir), probe_query=scenario.probe_query
    )

    LOG.info(
        "[%s] retrieved smart=%d mem=%d",
        scenario.id,
        len(smart_hits),
        len(mem_hits),
    )

    smart_score = score(
        ground_truth=scenario.ground_truth,
        probe=scenario.probe_query,
        retrieved=smart_hits,
    )
    mem_score = score(
        ground_truth=scenario.ground_truth,
        probe=scenario.probe_query,
        retrieved=mem_hits,
    )

    return ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category,
        ground_truth=scenario.ground_truth,
        probe_query=scenario.probe_query,
        project_dir=str(project_dir),
        session_id=session_id,
        replay_ok=replay_ok,
        replay_error=replay_error,
        systems=[
            SystemResult("claude-smart", smart_hits, smart_score, smart_notes),
            SystemResult("claude-mem", mem_hits, mem_score, mem_notes),
        ],
    )


def _aggregate(rows: list[ScenarioResult]) -> dict[str, dict[str, dict[str, float]]]:
    """Average recall and specificity per system per category.

    Returns:
        dict: ``{category: {system: {"recall": float, "specificity": float, "n": int}}}``.
            ``"overall"`` is included as a synthetic category.
    """
    buckets: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for r in rows:
        for key in (r.category, "overall"):
            by_system = buckets.setdefault(key, {})
            for sys_result in r.systems:
                by_system.setdefault(sys_result.system, []).append(
                    (sys_result.score.recall, sys_result.score.specificity)
                )
    agg: dict[str, dict[str, dict[str, float]]] = {}
    for cat, by_system in buckets.items():
        agg[cat] = {}
        for system, pairs in by_system.items():
            n = len(pairs)
            recall = sum(p[0] for p in pairs) / n if n else 0.0
            spec = sum(p[1] for p in pairs) / n if n else 0.0
            agg[cat][system] = {"recall": recall, "specificity": spec, "n": float(n)}
    return agg


def _write_json(rows: list[ScenarioResult], path: Path) -> None:
    """Dump raw rows as JSON for later analysis."""
    serializable = [
        {
            **asdict(r),
            "systems": [{**asdict(s), "score": asdict(s.score)} for s in r.systems],
        }
        for r in rows
    ]
    path.write_text(json.dumps(serializable, indent=2))


def _format_report(rows: list[ScenarioResult], agg: dict) -> str:
    """Render the Markdown comparison report."""
    lines: list[str] = []
    lines.append("# claude-mem vs claude-smart — memory capture benchmark")
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    lines.append(f"Scenarios run: {len(rows)}")
    lines.append("")

    lines.append("## Aggregate scores (0–3, higher is better)")
    lines.append("")
    lines.append("| Category | System | Recall | Specificity | N |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    category_order = [
        "personalization",
        "correction",
        "general",
        "learning",
        "overall",
    ]
    for cat in category_order:
        if cat not in agg:
            continue
        for system in sorted(agg[cat]):
            metrics = agg[cat][system]
            lines.append(
                f"| {cat} | {system} | {metrics['recall']:.2f} | "
                f"{metrics['specificity']:.2f} | {int(metrics['n'])} |"
            )
    lines.append("")

    lines.append("## Per-scenario detail")
    lines.append("")
    for r in rows:
        lines.append(f"### `{r.scenario_id}` ({r.category})")
        lines.append("")
        lines.append(f"- **Ground truth:** {r.ground_truth}")
        lines.append(f"- **Probe:** {r.probe_query}")
        if not r.replay_ok:
            lines.append(f"- **Replay failed:** {r.replay_error}")
        lines.append("")
        lines.append("| System | Recall | Specificity | Rationale | Rows |")
        lines.append("| --- | ---: | ---: | --- | ---: |")
        for s in r.systems:
            err = f" (error: {s.score.error})" if s.score.error else ""
            note = f" — {'; '.join(s.notes)}" if s.notes else ""
            rationale = (s.score.rationale or "").replace("|", "/")
            lines.append(
                f"| {s.system} | {s.score.recall} | {s.score.specificity} | "
                f"{rationale}{err}{note} | {len(s.retrieved)} |"
            )
        lines.append("")

    lines.append("## Cleanup")
    lines.append("")
    lines.append("Benchmark data lives under project paths matching `/tmp/membench/*`.")
    lines.append("To remove it:")
    lines.append("")
    lines.append("```bash")
    lines.append("claude-smart clear-all --yes   # removes ALL claude-smart memory")
    lines.append(
        "sqlite3 ~/.claude-mem/claude-mem.db "
        "\"DELETE FROM observations WHERE project LIKE '/tmp/membench/%'\""
    )
    lines.append("rm -rf /tmp/membench")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", help="Run a single scenario by id")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip replay; score whatever is already stored",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    """CLI entrypoint. Returns 0 on success, 1 on catastrophic harness failure."""
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    scenarios: list[Scenario] = list(SCENARIOS)
    if args.only:
        scenarios = [s for s in scenarios if s.id == args.only]
        if not scenarios:
            LOG.error("no scenario matches id=%s", args.only)
            return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"run-{ts}.json"
    md_path = RESULTS_DIR / f"report-{ts}.md"

    rows: list[ScenarioResult] = []
    for idx, scenario in enumerate(scenarios):
        if idx > 0 and not args.dry_run:
            time.sleep(INTER_SCENARIO_PAUSE_S)
        rows.append(_run_scenario(scenario, dry_run=args.dry_run))

    agg = _aggregate(rows)
    _write_json(rows, json_path)
    md_path.write_text(_format_report(rows, agg))

    LOG.info("wrote %s", json_path)
    LOG.info("wrote %s", md_path)
    print(f"\n=== report: {md_path} ===\n")
    print(md_path.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
