# Agent install instructions

> **You are an AI coding agent (e.g. Claude Code).** The user told you
> "Install ini https://github.com/arielfikru/claude-ask-gemini". Do exactly the
> steps below. They give you, the agent, a CLI to offload **visual analysis**
> (images, video, screenshots) to Gemini while you stay the orchestrator —
> filling the one gap text-only models can't: actually seeing pixels/frames.

## Steps

1. **Check the prerequisite.** This wraps the official Gemini CLI, so it must be
   installed and logged in:

   ```bash
   command -v gemini || npm install -g @google/gemini-cli
   gemini --version            # confirm it runs
   ```

   If `gemini` calls 401, the user must run `gemini login` (interactive OAuth).

2. **Clone** the repo to a temp dir and run the installer:

   ```bash
   tmp="$(mktemp -d)"
   git clone --depth 1 https://github.com/arielfikru/claude-ask-gemini.git "$tmp"
   bash "$tmp/install.sh"
   ```

   This copies `ask-gemini` + `ask-gemini-batch` into `~/.claude/bin`, installs
   the `/gemini` skill into `~/.claude/skills/gemini`, stages the optional MCP
   server in `~/.claude/mcp`, and adds `~/.claude/bin` to PATH.

3. **Verify** it works (use any local image):

   ```bash
   ask-gemini -f /path/to/image.png "what is in this image? one sentence"
   ```

   Expect a one-sentence description plus a usage line on stderr.

4. **(Optional) Register the MCP server** so MCP-native agents can call it
   without a shell:

   ```bash
   pip install 'mcp>=1.2.0'
   claude mcp add -s user gemini -- python3 ~/.claude/mcp/gemini-server.py
   ```

5. **From now on**, delegate any "look at this and tell me X" subtask (read a
   screenshot, spot a UI bug, summarize a video clip, OCR an image, compare two
   designs) to `ask-gemini` instead of guessing. Read
   `~/.claude/skills/gemini/SKILL.md` for when/how. You remain the orchestrator:
   validate Gemini's read before using it.

## Notes for the agent

- Subagents always run on your own model; you cannot make a subagent run Gemini.
  Delegation = calling the `ask-gemini` CLI via shell (or the MCP tool).
- **Not for image generation** — the Gemini CLI cannot generate AI images; it
  only draws primitives via code. Don't use this for "make me an illustration".
- The wrapper runs `gemini` from an empty temp dir and copies each `-f` file in,
  keeping calls lean (~8k tokens) and letting Gemini read media it sandboxes to
  the cwd. Don't bypass it by calling `gemini` directly for analysis.
- Auth is the Gemini CLI's own (OAuth, stored in `~/.gemini`). No API key env
  var needed.
