# caveman × claude-smart — Token-Savings Analysis

**Date:** 2026-07-06
**Repo:** `claude-smart-fork` @ `claude/caveman-savings-analysis`
**Method spec:** [2026-07-06-caveman-savings-analysis-spec.md](2026-07-06-caveman-savings-analysis-spec.md)
**Token unit:** tiktoken `cl100k_base` throughout.
**Tag legend:** **[M]** measured on real data · **[P]** projected (synthetic input
through the real renderer) · **[I]** indicative (real but n too small).

## Executive verdict

Coupling caveman with claude-smart to **save tokens is not justified by the
data.** The only token-compression lever — rendering claude-smart's injected
memory with the "compact" renderer when caveman is active — saves at best
**~1.5% of a session's input**, and at the shipped default settings it is
**net-negative** (the compact path is *larger* than normal at realistic memory
scale). The genuinely useful ideas (durable/project-scoped caveman preference,
dashboard visualization) do **not** depend on token savings and should be judged
on their own merits, not sold as efficiency wins.

Three hard numbers drive this:

1. **[M]** Current injection footprint is **0 tokens** — the local reflexio
   store has 0 distilled playbooks/preferences (46 raw interactions, nothing
   learned yet). There is nothing to compress today.
2. **[P]** At the shipped defaults (citations on, markdown links), the "compact"
   renderer is **−12% to −22%** *larger* than the normal renderer at 20–50
   learned items. It only compresses (~14%) with citations off.
3. **[M]** Even the *whole* injection is only **2–11%** of a median session's
   input (35,357 tok). A ~14% shave of an 11% slice is ~1.5% of the session —
   before the default-settings sign flip erases it.

## Channel 1 — injection weight, normal vs compact renderer

Rendered through the repo's real `context_format.render_inline_with_registry`
(normal) and `render_inline_compact_with_registry` (compact).

**[M] 1a — current real state:** `user_playbooks=0, agent_playbooks=0,
profiles=0` → both renderers return `""` → **0 tokens**. Injection footprint is
empty until reflexio distills playbooks/preferences.

**[P] 1b — synthetic scale, real renderer** (60% skills / 40% preferences):

| settings | N | normal | compact | delta | saved |
|---|---:|---:|---:|---:|---:|
| citations **on** (default) | 5 | 693 | 582 | 111 | **+16.0%** |
| citations **on** (default) | 20 | 1797 | 2022 | −225 | **−12.5%** |
| citations **on** (default) | 50 | 4005 | 4902 | −897 | **−22.4%** |
| citations **off** | 5 | 379 | 328 | 51 | +13.5% |
| citations **off** | 20 | 1483 | 1273 | 210 | +14.2% |
| citations **off** | 50 | 3691 | 3163 | 528 | +14.3% |

**Finding.** The compact renderer's *content* format is ~14% smaller (citations
off, all scales). But at the **default** (citations on) its compact citation
instruction builds a single marker that concatenates every item's linked
title+URL (`" | ".join(marker_parts)` in `_compact_citation_instruction`). That
marker grows with N and **overtakes the content savings past ~5 items**, making
"compact" a net *expansion* at realistic memory scale. This is a real
inefficiency in the compact citation path, independent of caveman.

## Channel 2 — share of session input

**[M] 2a — real now:** injection ≈ 0 tokens (0 learned items) → 0% of any
session today.

**[M] 2b — denominator + [P] projected share:** across 457 real transcripts the
median peak session input is **35,357 tokens** (p90 70,898). Against that, the
*normal*-rendered injection is:

| N (learned items) | injection tok | % of median session |
|---:|---:|---:|
| 5 | 693 | 2.0% |
| 20 | 1,797 | 5.1% |
| 50 | 4,005 | 11.3% |

Even a heavily-trained store (N=50) is ~11% of session input; the compressible
*delta* on top of that is the ~14%/−22% from Channel 1 — i.e. **~1.5% of the
session at best, negative at defaults.**

## Channel 3 — caveman output savings (reference)

**[M] but confounded.** 467 transcripts split by the `CAVEMAN MODE ACTIVE`
marker: 94 caveman-active / 373 inactive; assistant **text-block** tokens/msg
(thinking and tool_use excluded):

| group | n_msgs | median | mean | p90 |
|---|---:|---:|---:|---:|
| caveman-active | 3,039 | 29 | 81 | 241 |
| inactive | 2,768 | 20 | 97 | 249 |

Median is *higher* for caveman, mean is *lower* — the groups have different task
mixes (caveman-active sessions are recent heavy engineering work; inactive
includes many tiny/aborted sessions). **A cross-sectional comparison cannot
isolate caveman's effect**, so this neither confirms nor refutes caveman's ~65%
claim. The credible source for that figure is caveman's own same-session token
accounting (`/caveman-stats`), not this observational split. Reported honestly
as inconclusive.

## Channel 4 — overlap / second-order

**[I] unmeasurable.** Both local `~/.claude-smart/sessions` sessions are from the
caveman era; there is no caveman-off claude-smart baseline to compare interaction
volume against. n insufficient — no conclusion.

## Recommendation for the PR ideas

- **Bild 2 (caveman as a durable, project-scoped preference):** proceed *only*
  on its behavioral merit — making a session-scoped preference persist and
  auto-apply where it fits. **Do not frame it as token savings.** Feasibility
  boundary stands: extraction lives in the `reflexio` package; this repo can
  feed the signal and render/persist, not rewrite learning.
- **Bild 3 (dashboard visualization of caveman stats):** fine as a UI feature;
  no token-savings claim attached. Independent, low-risk.
- **Do NOT auto-switch to the compact renderer when caveman is active.** At
  default settings it *increases* injected tokens past ~5 learned items. If the
  compact path is ever wanted, first fix the citation-marker scaling — worth a
  separate upstream note to ReflexioAI regardless of caveman.

## Limitations

- 1b/2b steady-state figures are projections; synthetic item shapes match the
  `context_format` input contract but real distilled items may run longer/shorter.
- Channel 3 is confounded by task mix; treat as context, not proof.
- Local reflexio store is empty of learned items, so no channel has a large-N
  *measured* point — re-run the scripts after real usage accumulates.

## Reproducibility

```
uv run --with tiktoken python benchmarks/caveman/measure_injection.py
uv run --with tiktoken python benchmarks/caveman/measure_transcripts.py
CLAUDE_SMART_CITATIONS=off uv run --with tiktoken python benchmarks/caveman/measure_injection.py
```

Scripts read reflexio.db and transcripts read-only. Re-running refreshes the
**[M]** columns as the reflexio store fills; **[P]** columns are deterministic.
