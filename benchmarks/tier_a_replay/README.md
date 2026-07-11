# Tier A Replay Evaluation

This benchmark replays local Tier A claude-smart interactions twice:

- enabled arm: the current claude-smart retrieval context is supplied to Claude
- disabled arm: the same prompt is replayed without claude-smart learning

It then runs two judges:

- blind response-quality judge: compares only the two responses
- learning-attribution judge: sees the retrieved learning and decides whether the enabled arm was helped, hurt, unchanged, or inconclusive

Generated artifacts are written outside the repo:

```text
~/.claude-smart/evals/tier_a_replay/<run_id>/
```

This directory contains only the benchmark source and viewer template. Do not commit generated run directories, `dataset.jsonl`, `aggregate.json`, `report.md`, `impact_summary.*`, or generated `viewer.html` files.

## Requirements

- A local claude-smart installation with data in `~/.claude-smart` and `~/.reflexio`
- Claude Code CLI on `PATH` as `claude`
- claude-smart backend healthy
- Local filesystem paths referenced by the historical interactions available for read-only replay

The runner defaults to this checkout's `plugin/` directory for the hook preflight. To evaluate an installed plugin/cache instead, set:

```bash
export CLAUDE_SMART_PLUGIN_ROOT=/absolute/path/to/claude-smart/plugin
```

If older local data is missing a user id, the runner falls back to `CLAUDE_SMART_EVAL_USER_ID`, then `REFLEXIO_USER_ID`, then `default`:

```bash
export CLAUDE_SMART_EVAL_USER_ID=your-local-user-id
```

Preflight and postflight repo status checks default to this checkout and, when discoverable, its parent git checkout. Override them only if your benchmark checkout is embedded in another repo layout:

```bash
export TIER_A_REPLAY_REPO_STATUS_ROOT="$PWD"
export TIER_A_REPLAY_OUTER_REPO_STATUS_ROOT=/path/to/outer/repo
```

## Full Tier A Run

From the `claude-smart` repo root:

```bash
python3 benchmarks/tier_a_replay/run.py \
  --label tier_a_full_sonnet_opus \
  --case-limit 999 \
  --min-overlap 1.0 \
  --samples-per-arm 1 \
  --judge-passes 1 \
  --replay-model sonnet \
  --judge-model opus \
  --read-dir "$PWD"
```

Repeat `--read-dir` for any local source, docs, or worktree directories referenced by that machine's historical sessions. These directories are exposed to replay arms via `claude --add-dir` while the arms are otherwise constrained to read-oriented tools:

```text
Read,Glob,Grep,LS
```

Do not use the smoke defaults for a real evaluation; they only run three cases.

## What The Runner Does

1. Captures preflight state for repo status, `~/.reflexio` DB counts, `~/.claude-smart` session counts, and claude-smart logs.
2. Runs model availability probes for the replay and judge models.
3. Finds local Tier A candidates from `~/.claude-smart` sessions and historical citations.
4. Runs the live claude-smart hook preflight for each candidate and keeps only cases whose currently retrieved real IDs fully overlap historical cited real IDs when `--min-overlap 1.0` is used.
5. Replays each selected prompt from temporary per-arm directories:
   - enabled: plugin disabled, retrieved context injected explicitly
   - disabled: plugin disabled, no retrieved context
6. Validates both arms have matching tool/plugin surfaces, no disabled-arm injected IDs, no disabled-arm claude-smart marker, and successful return codes.
7. Runs the blind response judge.
8. Runs the learning-attribution judge using only the actual retrieved context supplied to the enabled arm, not historical cited records.
9. Writes reports and postflight state.

## Key Artifacts

Each run directory contains:

- `dataset.jsonl` - one row per judged comparison
- `aggregate.json` - machine-readable summary
- `report.md` - detailed run report
- `impact_summary.md` / `impact_summary.json` - compact outcome summary
- `viewer.html` - static browser viewer
- `candidate_preflights.json` - all candidate preflights
- `preflight.json` / `postflight.json` - containment and runtime snapshots
- `*_log_delta.txt` - log slices for the run
- per-case `assistant.txt`, `cmd.json`, and judge `stdout.json` files

The actual learning shown to the enabled arm is stored in each row at:

```text
preflight.retrieved_learning_context
preflight.retrieved_learning_records
```

## Viewer

The runner copies `benchmarks/tier_a_replay/viewer_template.html` into each run directory as generated `viewer.html`.

Serve the run directory:

```bash
cd ~/.claude-smart/evals/tier_a_replay/<run_id>
python3 -m http.server 8766 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8766/viewer.html
```

If the URL stops loading later, the temporary HTTP server probably exited. The HTML file is still in the run directory; restart the server from that directory.

## Validation Checklist

After a run completes, verify:

```bash
export RUN=~/.claude-smart/evals/tier_a_replay/<run_id>

python3 - <<'PY'
import json, os, pathlib
run = pathlib.Path(os.environ["RUN"]).expanduser()
rows = [json.loads(line) for line in (run / "dataset.jsonl").read_text().splitlines() if line.strip()]
agg = json.loads((run / "aggregate.json").read_text())
print(json.dumps(agg, indent=2, sort_keys=True))
assert agg["comparisons"] == len(rows)
assert agg["skipped_comparisons"] == 0
assert all((row.get("preflight") or {}).get("retrieved_learning_context") for row in rows)
assert all((row.get("response_judge") or {}).get("returncode") == 0 for row in rows)
assert all((row.get("attribution_judge") or {}).get("returncode") == 0 for row in rows)
PY
```

Check the viewer and data files:

```bash
curl -sS -I http://127.0.0.1:8766/viewer.html
curl -sS http://127.0.0.1:8766/aggregate.json
curl -sS http://127.0.0.1:8766/dataset.jsonl | wc -l
```

## Interpreting Results

Use the blind judge for raw response quality. Use the attribution judge for causal signal.

Good eval signals include:

- enabled wins and attribution says learning helped
- disabled wins and attribution says learning hurt
- enabled/disabled wins with attribution `none`, which means output quality changed for reasons not traceable to retrieved learning
- low consistency on reruns, which means the case may need multiple samples before drawing conclusions

The run should not modify the repository or create PRs. Runtime DB/log drift under `~/.claude-smart` and `~/.reflexio` is expected because the live claude-smart backend and hooks may process interactions during evaluation.
