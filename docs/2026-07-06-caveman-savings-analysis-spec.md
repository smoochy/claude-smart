# caveman × claude-smart — Token-Savings Analysis Spec

**Date:** 2026-07-06
**Repo:** `claude-smart-fork` (branch `claude/caveman-savings-analysis`)
**Status:** Methodology approved, pending spec review
**Type:** Evidence-based measurement study — NOT a feature. Produces a report that gates the decision to open any caveman-coupling PRs.

## Purpose

Before any caveman-coupling PR against `ReflexioAI/claude-smart`, quantify with
evidence where — if anywhere — running caveman together with claude-smart
actually saves tokens. The prior mengram experiment produced a misleading 0.5%
by measuring the wrong code path; this study exists to avoid repeating that.
Every number carries its status: **measured** (real data), **projected**
(synthetic input through the real renderer), or **indicative** (real but n too
small to generalize).

## Background facts established

- claude-smart injects learned **playbooks / preferences** into the prompt via
  `plugin/src/claude_smart/context_format.py`, which has two renderers:
  `render_inline_with_registry` (normal) and
  `render_inline_compact_with_registry` (compact). The compact path is the
  native coupling lever (caveman active → use compact).
- Preference/skill **extraction** lives in the separate `reflexio` package, not
  this repo. This study measures rendering/footprint, not extraction.
- Current local `~/.reflexio/data/reflexio.db` state: `profiles: 0`,
  `user_playbooks: 0`, `agent_playbooks: 0`, `interactions: 46`, `requests: 23`.
  **Zero distilled playbooks/preferences exist yet** — so the live injection
  footprint is currently ≈ nil. This is itself a finding and the reason
  channels 1–2 require synthetic projection for any steady-state claim.
- Data available: `~/.claude-smart/sessions/*.jsonl` (2 sessions),
  `~/.reflexio/data/reflexio.db`, `~/.claude/.caveman-active` (mode flag),
  ~467 Claude Code transcripts under `~/.claude/projects/**/*.jsonl`.

## Channels to measure

### Channel 1 — claude-smart injection weight (the coupling lever)

**Question:** How many input tokens does claude-smart's injected block cost, and
how much does the compact renderer save vs the normal renderer?

- **1a Measured (real, now):** Query `reflexio.db` for whatever playbooks /
  preferences exist. Render them through the repo's real
  `render_inline_with_registry` and `render_inline_compact_with_registry`.
  Count tokens (tiktoken `cl100k_base`) for each. Expected result given 0
  playbooks: ≈ 0 — report as "early-state footprint".
- **1b Projected (synthetic input, real renderer):** Construct realistic
  synthetic playbooks/preferences (shape matched to `context_format`'s expected
  structure) at N ∈ {5, 20, 50}. Render each set through BOTH real renderers.
  Report a token curve: normal vs compact vs absolute delta and % saved per N.
  This is the steady-state projection — labeled projection, but produced by the
  real rendering code, not an estimate.

**Evidence artifact:** table of (N, normal_tok, compact_tok, delta, pct) plus the
n=0 real snapshot.

### Channel 2 — share of a session's input tokens

**Question:** Does the injection footprint matter relative to total session
input? (Compressing 200 tokens inside a 50k-token session is noise.)

- **2a Measured (real):** In real transcripts that contain a claude-smart
  injection block, count injection tokens vs total input tokens for that turn /
  session. Report per-session share. Expected: near-0 now.
- **2b Projected:** Using Channel 1b's projected injection sizes against a
  representative real session's total input tokens (median from the 467
  transcripts), compute the projected share at N ∈ {5, 20, 50}. Report % of
  session the compact-renderer delta would actually save.

**Evidence artifact:** measured share table (real sessions) + projected share
table.

### Channel 3 — caveman output savings (reference magnitude)

**Question:** Verify caveman's own ~65% output-reduction claim on real data, as a
yardstick against the claude-smart numbers.

- **Measured (real):** Split the 467 transcripts into caveman-active vs inactive
  (detect via the caveman activation marker / session hook context present in
  the transcript). Compute assistant-output tokens per turn (or per assistant
  message) for each group. Report median tokens/turn and the reduction %.
- Guard against confounders: note that task mix differs between groups; report
  this as an observational comparison, not a controlled trial. If a
  same-session before/after caveman toggle exists, prefer it.

**Evidence artifact:** group medians, distribution summary, reduction %, n per
group.

### Channel 4 — overlap / second-order (indicative only)

**Question:** Does caveman's terser output change what claude-smart publishes to
reflexio (volume / content of interactions)?

- **Indicative (real, small n):** Compare `~/.claude-smart/sessions/*.jsonl`
  sizes and `reflexio.db` interaction counts between caveman-on and caveman-off
  sessions. With only 2 claude-smart sessions this cannot generalize — report
  explicitly as "indicative, n insufficient", state the direction if any, and
  do not draw a conclusion.

**Evidence artifact:** the raw two-to-few data points with an explicit
insufficient-n caveat.

## Method constraints

- Run all Python via `uv run` (never native python). tiktoken via
  `uv run --with tiktoken`; sqlite via stdlib `sqlite3`.
- Read-only against `reflexio.db`, `~/.claude-smart/`, and transcripts. Never
  mutate live state. Open the DB read-only (`file:...?mode=ro`) or copy first.
- Token counting standard: tiktoken `cl100k_base` for every count, so all
  channels are comparable. State this in the report.
- Rendering MUST use the repo's actual `context_format` functions — never a
  reimplementation — so Channel 1 reflects real behavior.
- Synthetic playbook/preference shapes must be justified against the real
  `context_format` input contract; include one real sample (from the DB if any
  appear, else the render-input schema) so a reviewer can judge realism.
- Every number in the report is tagged **measured / projected / indicative**.

## Deliverable

A single report `docs/2026-07-06-caveman-savings-analysis.md` in the fork:

1. Executive verdict (one paragraph): where coupling saves tokens, with the
   headline numbers and their status tags.
2. Per-channel section: question, method, evidence table, limitations.
3. A "current state" callout: 0 playbooks today → live footprint ≈ 0.
4. Recommendation for the two PR ideas (Bild 2 persistence, Bild 3 dashboard):
   proceed / defer / drop, justified by the numbers.
5. Reproducibility appendix: the exact commands / scripts used, so the study can
   be re-run when more playbooks have accumulated.

Measurement scripts live under `benchmarks/caveman/` in the fork (kept, so the
study is repeatable), committed separately from the report.

## Success criteria

- No unlabeled numbers — each is measured, projected, or indicative.
- Channel 1 uses the real renderers; Channel 3 uses real transcripts.
- The report states plainly whether the coupling is worth a PR, given that the
  savings ceiling is what the data shows, not what the concept promises.
- Reproducible: a second run after more usage would refresh the measured columns
  without rewriting method.

## Open questions for spec review

1. caveman-active detection in transcripts: confirm the exact marker string the
   caveman hook injects (e.g. "CAVEMAN MODE ACTIVE") so Channel 3's split is
   reliable — pin it during execution by grepping a known caveman session.
2. Session total-input token counting: whole-session cumulative vs per-turn
   average — the report will use per-turn average for Channel 2 and state it.
