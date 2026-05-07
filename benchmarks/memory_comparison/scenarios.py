"""Ground-truth scenarios for the claude-mem vs claude-smart benchmark.

Each scenario scripts a short multi-turn Claude CLI conversation. Both plugins
observe the session via their hooks and independently extract memory. After
the session, ``probe_query`` is fired at each system and the retrieved text
is scored against ``ground_truth`` by an LLM judge.

Categories (8 scenarios each, 32 total):
    - personalization: durable user preferences ("I always use X")
    - correction: user pushes back on the assistant's approach
    - general: role, team, or project context that should persist
    - learning: probes that ask for a *rule to apply going forward*, not
      "what happened before". Exposes whether a system produces behavioral
      rules (claude-smart) or only descriptive history (claude-mem). Both
      systems see identical source turns; the probe is the differentiator.

Fairness notes:
    - Each scenario states its rule/fact explicitly in at least one user
      turn so neither extractor's prompt design bias dominates.
    - Phrasing varies across scenarios (explicit prohibition, narrative
      report, contextual aside) to avoid favoring a single extraction
      pattern.
    - Both systems receive the identical ``turns`` tuple via their native
      ingestion path; only the post-extraction retrieval is scored.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """A single benchmark case.

    Attributes:
        id (str): Stable slug, used for scratch dir + result keying.
        category (str): One of ``personalization``, ``correction``,
            ``general``, ``learning``.
        turns (tuple[str, ...]): User messages delivered in order; each turn
            is one Claude session (first via ``-p``, rest via ``--resume``).
        ground_truth (str): The fact or rule we expect both systems to
            capture.
        probe_query (str): Retrieval query fired at each system post-session.
    """

    id: str
    category: str
    turns: tuple[str, ...]
    ground_truth: str
    probe_query: str


SCENARIOS: tuple[Scenario, ...] = (
    # ---------- personalization (8) ----------
    Scenario(
        id="pref-testfmk",
        category="personalization",
        turns=(
            "I'm starting a new Python project. Give me a one-line summary "
            "of what test framework you'd suggest.",
            "I always use pytest, never unittest — make that a project-wide "
            "rule for me going forward.",
            "Good. Write a one-line sample test for a function add(a, b).",
        ),
        ground_truth="User prefers pytest over unittest as a project-wide rule.",
        probe_query="What Python test framework does the user prefer?",
    ),
    Scenario(
        id="pref-formatting",
        category="personalization",
        turns=(
            "What indent style is most common in Python?",
            "For my code, always use 4-space indents and double quotes — "
            "don't ever suggest tabs or single quotes.",
            "Show a one-line example of a dict literal in my preferred style.",
        ),
        ground_truth=(
            "User requires 4-space indents and double quotes in Python code; "
            "no tabs, no single quotes."
        ),
        probe_query="What formatting style does the user require for Python code?",
    ),
    Scenario(
        id="pref-stack",
        category="personalization",
        turns=(
            "I'm picking a deployment target for a small API.",
            "I deploy everything on Railway and always use Postgres over "
            "MySQL — remember that for all my projects.",
            "Given that, suggest a one-line DATABASE_URL env var format.",
        ),
        ground_truth=(
            "User deploys on Railway and prefers Postgres over MySQL "
            "across all projects."
        ),
        probe_query="Where does the user deploy and what database do they prefer?",
    ),
    Scenario(
        id="pref-pkgmgr",
        category="personalization",
        turns=(
            "Quick note about my Python tooling.",
            "I use uv for everything — uv pip, uv run, uv venv. Never "
            "suggest plain pip or virtualenv to me; uv is the only package "
            "manager I want in any project.",
            "Got it. Show one line for installing httpx in my workflow.",
        ),
        ground_truth=(
            "User uses uv exclusively for Python package management; never "
            "suggest plain pip, virtualenv, or poetry."
        ),
        probe_query="Which Python package manager does the user use?",
    ),
    Scenario(
        id="pref-langchoice",
        category="personalization",
        turns=(
            "I'm spinning up a new web service repo.",
            "Default me to TypeScript for any new repo — I haven't written "
            "plain JavaScript in years and don't want any new .js files in "
            "anything I scaffold.",
            "Acknowledged. One-line example of a strongly-typed function "
            "signature in my preferred language.",
        ),
        ground_truth=(
            "User defaults to TypeScript for all new repos; do not produce "
            "plain JavaScript (.js) files."
        ),
        probe_query="Should new code in this user's projects be TypeScript or JavaScript?",
    ),
    Scenario(
        id="pref-loglevel",
        category="personalization",
        turns=(
            "Question about logging conventions.",
            "I always emit structured JSON logs (one JSON object per line) "
            "and never plain-text logs. Use that style by default in any "
            "logging I ask you to add.",
            "Show a one-line example of a structured INFO log in my style.",
        ),
        ground_truth=(
            "User requires structured JSON logs (one JSON object per line); "
            "do not emit plain-text logs."
        ),
        probe_query="What logging format does the user use?",
    ),
    Scenario(
        id="pref-commits",
        category="personalization",
        turns=(
            "Style note for any commits you draft for me.",
            "All my commits use Conventional Commits (feat:, fix:, chore:, "
            "etc.). No exceptions, ever — even tiny commits get a type "
            "prefix.",
            "Draft a one-line commit message for adding a README typo fix.",
        ),
        ground_truth=(
            "User requires Conventional Commits format (feat:, fix:, "
            "chore:, etc.) on every commit, including tiny ones."
        ),
        probe_query="What commit message format does the user require?",
    ),
    Scenario(
        id="pref-shell",
        category="personalization",
        turns=(
            "Heads-up about my shell environment.",
            "I use fish, not bash or zsh. Any shell snippets you write for "
            "me should be valid fish syntax — no `export FOO=bar`, use "
            "`set -x FOO bar` instead.",
            "Show me a one-line fish-style snippet exporting an API_KEY env var.",
        ),
        ground_truth=(
            "User uses fish shell; shell snippets must use fish syntax "
            "(e.g., `set -x FOO bar`), not bash/zsh `export`."
        ),
        probe_query="Which shell does the user use, and what syntax should snippets follow?",
    ),
    # ---------- correction (8) ----------
    Scenario(
        id="corr-async",
        category="correction",
        turns=(
            "Write a one-line Python function fetch_user(id) that calls an "
            "HTTP API using httpx.",
            "Stop using async — this codebase is fully synchronous. "
            "Never write async code in this project.",
            "Rewrite the function synchronously in one line.",
        ),
        ground_truth=(
            "User corrected: this codebase is synchronous; do not write async "
            "code in this project."
        ),
        probe_query="Should async code be used in this project?",
    ),
    Scenario(
        id="corr-verbose",
        category="correction",
        turns=(
            "Write a one-line function square(x) with a full docstring.",
            "No, stop writing docstrings and comments — I want terse code "
            "only. Keep it minimal from now on.",
            "Rewrite square(x) in your new style, one line.",
        ),
        ground_truth=(
            "User corrected: no docstrings or comments; keep code terse and minimal."
        ),
        probe_query="Does the user want docstrings and comments in their code?",
    ),
    Scenario(
        id="corr-lib",
        category="correction",
        turns=(
            "Give me a one-line snippet to parse a YAML file in Python.",
            "No, don't use PyYAML — it's insecure. We only use ruamel.yaml "
            "in this project. Stick to that.",
            "Redo it in one line with the right library.",
        ),
        ground_truth=(
            "User corrected: do not use PyYAML due to security; use "
            "ruamel.yaml in this project."
        ),
        probe_query="What YAML library should be used in this project, and what should be avoided?",
    ),
    Scenario(
        id="corr-mocks",
        category="correction",
        turns=(
            "Sketch a one-line pytest test that hits the user-create "
            "endpoint with a mocked database session.",
            "Don't mock the database in integration tests — we got burned "
            "last quarter when mocked tests passed but the real migration "
            "broke prod. Always use a real Postgres in these tests.",
            "Redo the test against a real Postgres in one line.",
        ),
        ground_truth=(
            "User corrected: integration tests must hit a real Postgres, "
            "not a mocked DB; reason — past incident where mocked tests "
            "masked a broken migration."
        ),
        probe_query="Should the database be mocked in integration tests?",
    ),
    Scenario(
        id="corr-summary",
        category="correction",
        turns=(
            "Add a getter for the user's email to the User model in one line.",
            "Stop summarizing what you just did at the end of every "
            "response — I can read the diff. From now on, just make the "
            "change and stop talking.",
            "Make the requested change and stop.",
        ),
        ground_truth=(
            "User corrected: do not add trailing summaries explaining what "
            "the diff did; reply terse, no recap."
        ),
        probe_query="Should the assistant include a recap or summary at the end of responses?",
    ),
    Scenario(
        id="corr-overeng",
        category="correction",
        turns=(
            "Add a JSON file loader and a YAML file loader as separate "
            "module-level helpers.",
            "Stop adding factory classes and abstract base classes for two "
            "implementations — that's overengineering. Inline the two "
            "loaders. Don't introduce abstractions until there are at least "
            "three concrete cases.",
            "Inline both loaders without any factory or ABC.",
        ),
        ground_truth=(
            "User corrected: do not introduce factory classes or ABCs for "
            "fewer than three concrete cases; inline duplicates instead."
        ),
        probe_query="When should I introduce factory or ABC abstractions in this project?",
    ),
    Scenario(
        id="corr-emoji",
        category="correction",
        turns=(
            "Write a one-line success log message after a deploy completes.",
            "No emojis — anywhere. Not in logs, not in code, not in commit "
            "messages, not in PR titles. We had to scrub them out of CI "
            "output and it broke parsers downstream.",
            "Rewrite the log message without any emoji.",
        ),
        ground_truth=(
            "User corrected: no emojis anywhere — code, logs, commit "
            "messages, PR titles; reason — broke downstream parsers."
        ),
        probe_query="Are emojis allowed in code, logs, or commit messages in this project?",
    ),
    Scenario(
        id="corr-trailers",
        category="correction",
        turns=(
            "Draft a one-line commit message for a small bug fix.",
            "Don't add `Co-Authored-By: Claude ...` trailers to my commits "
            "— ever. Our internal tooling parses commit metadata and the "
            "AI-generated trailers confuse it.",
            "Redraft the commit message with no trailers at all.",
        ),
        ground_truth=(
            "User corrected: never add Co-Authored-By: Claude trailers to "
            "commits; reason — internal tooling parses commit metadata."
        ),
        probe_query="Should commit messages include a Co-Authored-By trailer?",
    ),
    # ---------- general (8) ----------
    Scenario(
        id="gen-role",
        category="general",
        turns=(
            "Hi, I want to ask about observability tooling.",
            "Context for you: I'm a data scientist, and I'm currently "
            "investigating what logging and tracing we have in our ETL "
            "pipelines.",
            "Given that context, name one tool I should look into. One line.",
        ),
        ground_truth=(
            "User is a data scientist currently working on observability "
            "and logging for ETL pipelines."
        ),
        probe_query="What is the user's role and current focus?",
    ),
    Scenario(
        id="gen-team",
        category="general",
        turns=(
            "Quick planning question about releases.",
            "Context: I maintain the billing service. My team is 3 people "
            "and we ship every Friday. Remember that.",
            "Given that cadence, when should I cut a release branch for a "
            "change merging Wednesday? One line.",
        ),
        ground_truth=(
            "User maintains the billing service on a 3-person team with "
            "weekly Friday releases."
        ),
        probe_query="What service does the user own and what is their release cadence?",
    ),
    Scenario(
        id="gen-freeze",
        category="general",
        turns=(
            "I'm prioritizing merges this week.",
            "Heads up — we're freezing all non-critical merges after "
            "Thursday because the mobile team is cutting a release branch. "
            "Keep that in mind for any PR work.",
            "Given that, should a nice-to-have refactor PR ship today or wait? One line.",
        ),
        ground_truth=(
            "Merge freeze for non-critical PRs starts after Thursday due to "
            "the mobile release-branch cut."
        ),
        probe_query="Is there a merge freeze coming up, and why?",
    ),
    Scenario(
        id="gen-stack",
        category="general",
        turns=(
            "Architecture context for our app.",
            "Backend is all Go (chi router, sqlx). Frontend is React with "
            "TypeScript and Vite. We don't use Next.js anywhere — pure SPA. "
            "Keep that in mind for any code you suggest.",
            "Given the stack, name one library I'd use for state management on the frontend. One line.",
        ),
        ground_truth=(
            "Stack: Go (chi + sqlx) on the backend, React + TypeScript + "
            "Vite SPA on the frontend; no Next.js."
        ),
        probe_query="What is this project's tech stack on backend and frontend?",
    ),
    Scenario(
        id="gen-oncall",
        category="general",
        turns=(
            "I might be a bit slow this week.",
            "I'm primary oncall for the API gateway team this week and "
            "watching the request-latency Grafana dashboard. Pages route to "
            "me first until Monday.",
            "If a non-urgent code review request comes in, what should I tell the requester? One line.",
        ),
        ground_truth=(
            "User is primary oncall for the API gateway team this week, "
            "monitoring request-latency Grafana dashboard, until Monday."
        ),
        probe_query="What is the user's oncall status this week?",
    ),
    Scenario(
        id="gen-deadline",
        category="general",
        turns=(
            "Project status note.",
            "We launch the new checkout flow on June 15. Scope is frozen — "
            "no new features land before launch, only bug fixes. Anything "
            "outside that scope gets parked for the next milestone.",
            "Should a small UX polish PR land before launch? One line.",
        ),
        ground_truth=(
            "Checkout-flow launch is June 15; scope is frozen — only bug "
            "fixes land before launch, no new features."
        ),
        probe_query="When does the checkout flow launch and what is the scope policy until then?",
    ),
    Scenario(
        id="gen-customers",
        category="general",
        turns=(
            "Compliance reminder for any data-handling code you write.",
            "We're a B2B SaaS and 100% of our customers are based in the "
            "EU. All data must stay in EU-region storage; never write code "
            "that ships data through US-region endpoints or services.",
            "If I add a new third-party API call, what's the first thing to verify? One line.",
        ),
        ground_truth=(
            "All customers are EU-based; data must stay in EU-region "
            "storage; do not route through US-region endpoints."
        ),
        probe_query="What region constraint applies to data and third-party services in this project?",
    ),
    Scenario(
        id="gen-arch",
        category="general",
        turns=(
            "Repo layout context.",
            "We have a monorepo with three services: `auth` (Python "
            "FastAPI), `billing` (Node/NestJS), and `analytics` (Go). They "
            "share a common protobuf-defined gRPC contract. Cross-service "
            "calls go over gRPC, never HTTP.",
            "If `billing` needs to call `auth`, what protocol should it use? One line.",
        ),
        ground_truth=(
            "Monorepo with three services: auth (FastAPI), billing "
            "(NestJS), analytics (Go); cross-service calls use gRPC, never HTTP."
        ),
        probe_query="What services exist in this monorepo and how do they communicate?",
    ),
    # ---------- learning (8) ----------
    # Each: user reports a past event. Probe asks for a FUTURE-FACING RULE.
    # A pure memory system surfaces the event description; a learning
    # system produces the rule. Ground truth is the rule, not the event.
    Scenario(
        id="learn-api-v2",
        category="learning",
        turns=(
            "Quick note on our internal-api client.",
            "We migrated every call in the codebase from internal-api v1 to "
            "v2 last sprint. v1 is going away — any new code should target "
            "v2 going forward.",
            "Got it. Paste me a one-line import for the v2 client.",
        ),
        ground_truth=(
            "Behavioral rule: new code must use internal-api v2; do not "
            "suggest or write v1 calls."
        ),
        probe_query=(
            "When I add a new internal-api call in this project, which "
            "version should I use, and is there a version I should avoid?"
        ),
    ),
    Scenario(
        id="learn-naming",
        category="learning",
        turns=(
            "Style question for this project.",
            "We just refactored every identifier in the repo from snake_case "
            "(usr_id, fetch_data) to camelCase (userId, fetchData). That's "
            "now the house convention for all new TS code.",
            "Acknowledged. Give me a one-line type alias for a user-id field "
            "in your preferred style.",
        ),
        ground_truth=(
            "Behavioral rule: all new TS identifiers in this project use "
            "camelCase; do not write snake_case identifiers."
        ),
        probe_query=(
            "What naming convention should I use for new identifiers in this "
            "project's TypeScript code?"
        ),
    ),
    Scenario(
        id="learn-pagination",
        category="learning",
        turns=(
            "I want to flag a bug class to watch out for.",
            "We just fixed an off-by-one in our pagination helper — the "
            "`offset + limit` calculation was computing the LAST index "
            "instead of the COUNT. Same bug shape has now bitten us three "
            "times in different files. Treat pagination boundary math as a "
            "high-risk area going forward.",
            "Understood. Write a one-line assertion I could add in review.",
        ),
        ground_truth=(
            "Behavioral rule: treat pagination offset/limit boundary math "
            "as high-risk; verify offset-vs-count semantics and add "
            "boundary-value tests."
        ),
        probe_query=(
            "What should I double-check or test whenever I touch pagination "
            "code in this project?"
        ),
    ),
    Scenario(
        id="learn-timezones",
        category="learning",
        turns=(
            "Bug postmortem note.",
            "We had a P1 last week where a billing job ran on naive "
            "datetimes and double-charged customers when DST shifted. "
            "Fixed by switching every datetime in the codebase to "
            "tz-aware UTC. New code must always use tz-aware UTC datetimes "
            "— never naive.",
            "Got it. One-line snippet creating a tz-aware UTC `now`.",
        ),
        ground_truth=(
            "Behavioral rule: always use tz-aware UTC datetimes; never use "
            "naive datetimes (caused a P1 DST double-charge incident)."
        ),
        probe_query=(
            "What datetime convention should I use for any new datetime "
            "code in this project?"
        ),
    ),
    Scenario(
        id="learn-rate-limit",
        category="learning",
        turns=(
            "Lesson learned this week.",
            "Our integration with the payments provider went down for an "
            "hour because we didn't retry on HTTP 429. Now any external "
            "API call in this codebase must implement exponential-backoff "
            "retries on 429 and 5xx responses. Treat that as mandatory for "
            "all new HTTP client code.",
            "Understood. Sketch a one-line retry-decorator usage.",
        ),
        ground_truth=(
            "Behavioral rule: every new external HTTP client call must "
            "implement exponential-backoff retries on HTTP 429 and 5xx; "
            "reason — past outage from missing 429 retry."
        ),
        probe_query=(
            "What retry behavior is required for any new external HTTP "
            "API call in this project?"
        ),
    ),
    Scenario(
        id="learn-secrets",
        category="learning",
        turns=(
            "Security incident note.",
            "We leaked an API key into our log aggregator last month — it "
            "was a `print(request.headers)` that captured an Authorization "
            "header. New rule: any code that logs request/response data "
            "must redact tokens, API keys, cookies, and Authorization "
            "headers before they hit any logger.",
            "Acknowledged. One-line example of a redacted-headers log.",
        ),
        ground_truth=(
            "Behavioral rule: redact tokens, API keys, cookies, and "
            "Authorization headers before logging request/response data; "
            "reason — past leak via unredacted header logging."
        ),
        probe_query=(
            "What must I do before logging request or response data in this project?"
        ),
    ),
    Scenario(
        id="learn-nplus1",
        category="learning",
        turns=(
            "Performance bug we just shipped.",
            "Our `/orders` endpoint was doing N+1 queries — iterating "
            "orders and lazy-loading the customer for each row. Fixed by "
            "switching to eager-loading with a join. New rule: when you "
            "iterate ORM rows in a hot path, always eager-load the "
            "relations you'll touch in the loop.",
            "Got it. Sketch a one-line eager-load query for orders + customers.",
        ),
        ground_truth=(
            "Behavioral rule: when iterating ORM rows in a hot path, "
            "always eager-load the relations accessed in the loop; reason "
            "— past N+1 perf bug on /orders."
        ),
        probe_query=(
            "What should I do when iterating ORM rows in a hot path in this project?"
        ),
    ),
    Scenario(
        id="learn-cors",
        category="learning",
        turns=(
            "Security review takeaway from last sprint.",
            "We had a `Access-Control-Allow-Origin: *` in our internal "
            "admin API that pen-test flagged as a vulnerability. Fixed by "
            "switching to an exact-origin whitelist. New rule for any HTTP "
            "endpoint we add: never use a wildcard CORS origin — always "
            "whitelist exact origins from a config list.",
            "Understood. Sketch a one-line CORS middleware config.",
        ),
        ground_truth=(
            "Behavioral rule: never use wildcard `*` CORS origins; always "
            "whitelist exact origins from a config list; reason — past "
            "pen-test finding on internal admin API."
        ),
        probe_query=(
            "What CORS-origin policy applies to any new HTTP endpoint in this project?"
        ),
    ),
)
