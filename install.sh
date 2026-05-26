#!/usr/bin/env bash
# Installer for claude-ask-gemini.
# Idempotent: copies the CLIs + skill into ~/.claude, wires PATH, stages the MCP server.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing ask-gemini into $CLAUDE_DIR"
mkdir -p "$CLAUDE_DIR/bin" "$CLAUDE_DIR/skills/gemini" "$CLAUDE_DIR/mcp"

install -m 0755 "$SRC/bin/ask-gemini.py" "$CLAUDE_DIR/bin/ask-gemini.py"
ln -sf "$CLAUDE_DIR/bin/ask-gemini.py" "$CLAUDE_DIR/bin/ask-gemini"
install -m 0755 "$SRC/bin/ask-gemini-batch.py" "$CLAUDE_DIR/bin/ask-gemini-batch.py"
ln -sf "$CLAUDE_DIR/bin/ask-gemini-batch.py" "$CLAUDE_DIR/bin/ask-gemini-batch"
install -m 0644 "$SRC/skills/gemini/SKILL.md" "$CLAUDE_DIR/skills/gemini/SKILL.md"
install -m 0644 "$SRC/mcp/server.py" "$CLAUDE_DIR/mcp/gemini-server.py"

# Wire PATH into the user's shell rc (bash + zsh), once.
add_path() {
  local rc="$1"
  [ -f "$rc" ] || return 0
  grep -q 'claude/bin (ask-gemini)' "$rc" && return 0
  {
    echo ''
    echo '# claude/bin (ask-gemini)'
    echo 'export PATH="$HOME/.claude/bin:$PATH"'
  } >> "$rc"
  echo "==> Added PATH to $rc"
}
add_path "$HOME/.bashrc"
add_path "$HOME/.zshrc"

echo ""
echo "Done. CLIs: ask-gemini, ask-gemini-batch   Skill: /gemini"
echo ""
echo "PREREQ: the Gemini CLI must be installed and logged in:"
echo "  npm install -g @google/gemini-cli   # or your package manager"
echo "  gemini login                        # OAuth, one time"
echo ""
echo "Test:  ask-gemini -f some-image.png 'what is in this image?'"
echo ""
echo "Optional MCP (call from MCP-native agents without a shell):"
echo "  claude mcp add -s user gemini -- python3 $CLAUDE_DIR/mcp/gemini-server.py"
echo "  (needs: pip install 'mcp>=1.2.0')"
