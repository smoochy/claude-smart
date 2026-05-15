#!/usr/bin/env bash
# One-shot local-dev setup for claude-smart.
#
# Does what the published install wrapper does for end users, plus the
# extra steps that only make sense when you're iterating on this repo:
#   1. Initialize the reflexio submodule.
#   2. Uncomment the `[tool.uv.sources]` block in plugin/pyproject.toml so
#      uv resolves reflexio-ai from the vendored submodule (editable).
#   3. `git update-index --skip-worktree` plugin/pyproject.toml + uv.lock
#      so the local divergence is invisible to `git status`.
#   4. `uv sync` from plugin/.
#   5. Append CLAUDE_SMART_USE_LOCAL_CLI=1 / _USE_LOCAL_EMBEDDING=1 to
#      ~/.reflexio/.env so reflexio runs without any external API key.
#   6. Prepare and register the local marketplace with Claude Code (user scope) so
#      `claude-smart@reflexioai-local` is available everywhere.
#   7. Wire this repo's .claude/settings.local.json to enable the local
#      plugin and shadow the remote one for this project.
#
# Idempotent: safe to re-run.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
PLUGIN_ROOT="$REPO_ROOT/plugin"
PYPROJECT="$PLUGIN_ROOT/pyproject.toml"
LOCKFILE="$PLUGIN_ROOT/uv.lock"

log() { printf '[setup-local-dev] %s\n' "$*" >&2; }

log "initializing reflexio submodule..."
(cd "$REPO_ROOT" && git submodule update --init --recursive reflexio)

log "enabling [tool.uv.sources] override in plugin/pyproject.toml..."
# Use an absolute path for the reflexio submodule. Relative paths like
# "../reflexio" get resolved by uv against the literal --project path,
# which breaks when slash commands pass the ~/.reflexio/plugin-root
# symlink (uv does not canonicalize) — it would resolve to
# $HOME/.reflexio/reflexio, which does not exist.
REFLEXIO_ABS="$REPO_ROOT/reflexio"
sed -i.bak -E \
  -e 's|^# \[tool\.uv\.sources\]$|[tool.uv.sources]|' \
  -e "s|^(# )?reflexio-ai = \\{ path = \"[^\"]*\", editable = true \\}\$|reflexio-ai = { path = \"$REFLEXIO_ABS\", editable = true }|" \
  "$PYPROJECT"
rm -f "$PYPROJECT.bak"

# Hide local divergence in pyproject.toml + uv.lock from `git status`. See
# DEVELOPER.md ("Developing locally") for the rationale.
git -C "$REPO_ROOT" update-index --skip-worktree plugin/pyproject.toml plugin/uv.lock

if ! command -v uv >/dev/null 2>&1; then
  log "ERROR: uv not found — install it from https://docs.astral.sh/uv/ first."
  exit 1
fi
log "running uv sync in plugin/ ..."
(cd "$PLUGIN_ROOT" && uv sync --quiet)

REFLEXIO_ENV="$HOME/.reflexio/.env"
mkdir -p "$(dirname "$REFLEXIO_ENV")"
touch "$REFLEXIO_ENV"
if ! grep -q '^CLAUDE_SMART_USE_LOCAL_CLI=' "$REFLEXIO_ENV"; then
  printf '\n# Route reflexio generation through the local Claude Code CLI\nCLAUDE_SMART_USE_LOCAL_CLI=1\n' >> "$REFLEXIO_ENV"
  log "appended CLAUDE_SMART_USE_LOCAL_CLI=1 to $REFLEXIO_ENV"
fi
if ! grep -q '^CLAUDE_SMART_USE_LOCAL_EMBEDDING=' "$REFLEXIO_ENV"; then
  printf '# Use the in-process ONNX embedder (chromadb) — no API key for semantic search\nCLAUDE_SMART_USE_LOCAL_EMBEDDING=1\n' >> "$REFLEXIO_ENV"
  log "appended CLAUDE_SMART_USE_LOCAL_EMBEDDING=1 to $REFLEXIO_ENV"
fi

# Prepare and register the local marketplace with Claude Code (user-scope).
# local-marketplace/ is gitignored because it contains a symlink to this
# checkout's plugin/ directory. Its manifest declares name=reflexioai-local —
# distinct from the remote `reflexioai`, so both can coexist in Claude Code's
# marketplace list.
LOCAL_MKT_DIR="$REPO_ROOT/local-marketplace"
log "preparing local marketplace at $LOCAL_MKT_DIR..."
mkdir -p "$LOCAL_MKT_DIR/.claude-plugin"
python3 - "$REPO_ROOT/.claude-plugin/marketplace.json" "$LOCAL_MKT_DIR/.claude-plugin/marketplace.json" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
data = json.loads(src.read_text())
data["name"] = "reflexioai-local"
data["plugins"][0]["source"] = "./plugin"
dst.write_text(json.dumps(data, indent=2) + "\n")
PY
rm -rf "$LOCAL_MKT_DIR/plugin"
ln -sfn "$PLUGIN_ROOT" "$LOCAL_MKT_DIR/plugin"

if command -v claude >/dev/null 2>&1; then
  log "registering local marketplace with Claude Code..."
  # `claude plugin marketplace add` errors if already registered; treat
  # that as a no-op. Output goes to stderr so we can keep logs clean.
  if claude plugin marketplace add "$LOCAL_MKT_DIR" >/dev/null 2>&1; then
    log "  added reflexioai-local → $LOCAL_MKT_DIR"
  else
    log "  reflexioai-local already registered (or add failed — run manually to debug)"
  fi
else
  log "WARNING: 'claude' CLI not on PATH — skipping marketplace registration."
  log "  Run it later: claude plugin marketplace add $LOCAL_MKT_DIR"
fi

# Project-scoped enable/disable: turn on the local plugin and shadow the
# remote one for this repo so they don't stack. The marketplace itself is
# already registered at user scope above.
SETTINGS_DIR="$REPO_ROOT/.claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.local.json"
mkdir -p "$SETTINGS_DIR"
python3 - "$SETTINGS_FILE" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])

data: dict = {}
if settings_path.is_file():
    try:
        data = json.loads(settings_path.read_text() or "{}")
    except json.JSONDecodeError:
        print(
            f"[setup-local-dev] ERROR: {settings_path} is not valid JSON; "
            "refusing to overwrite",
            file=sys.stderr,
        )
        sys.exit(1)

if not isinstance(data, dict):
    print(
        f"[setup-local-dev] ERROR: {settings_path} top-level is not a JSON object",
        file=sys.stderr,
    )
    sys.exit(1)

enabled = data.setdefault("enabledPlugins", {})
enabled["claude-smart@reflexioai-local"] = True
# Shadow the remote so both don't load side-by-side in this repo.
enabled["claude-smart@reflexioai"] = False

settings_path.write_text(json.dumps(data, indent=2) + "\n")
PY
log "wrote $SETTINGS_FILE (claude-smart@reflexioai-local enabled, @reflexioai shadowed off)"

# Force-point ~/.reflexio/plugin-root at this repo's plugin/ so slash
# commands resolve to editable in-repo sources (not the marketplace
# cache). SessionStart's non-force self-heal will respect this link.
# Warn (don't abort) on failure — marketplace registration and settings
# have already been committed by this point, so aborting would leave the
# user in a half-configured state.
if ! bash "$PLUGIN_ROOT/scripts/ensure-plugin-root.sh" "$PLUGIN_ROOT" --force; then
  log "WARNING: ensure-plugin-root failed; rerun manually:"
  log "  bash $PLUGIN_ROOT/scripts/ensure-plugin-root.sh $PLUGIN_ROOT --force"
fi

log ""
log "done. Restart Claude Code to pick up the local plugin."
log "  pyproject.toml → editable reflexio-ai from ../reflexio"
log "  ~/.reflexio/.env → local-CLI + local-embedding providers"
log "  user marketplaces → reflexioai-local ($LOCAL_MKT_DIR)"
log "  .claude/settings.local.json → claude-smart@reflexioai-local"
