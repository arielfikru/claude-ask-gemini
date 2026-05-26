# claude-ask-gemini

Give your AI coding agent (Claude Code) a pair of **eyes**: it hands visual work
— screenshots, photos, diagrams, UI mockups, video clips — to **Gemini**
(`gemini-3.1-pro`) via the official [Gemini CLI](https://github.com/google-gemini/gemini-cli),
then reviews the read before acting on it.

**The intern model.** The agent is the senior; Gemini is the **vision intern**
working under it: the senior briefs a precise question and passes the media (the
intern sees only what you hand it), the intern looks at the pixels/frames and
answers, and the senior **reviews and corrects** before using the result. This
fills the one gap text-only models (Claude inline, DeepSeek) can't — actually
*seeing* an image or video. Companion to
[claude-use-deepseek](https://github.com/arielfikru/claude-use-deepseek) (the
text intern).

> **Not an image generator.** The Gemini CLI cannot generate AI images — it only
> reads/analyzes them. This tool is for *understanding* media, not creating it.

## Install — just tell your agent

Paste this to Claude Code (or any agent that can run shell + clone repos):

```
Install ini https://github.com/arielfikru/claude-ask-gemini
```

The agent reads [`INSTALL.md`](INSTALL.md) and sets itself up. That's it.

### Manual install

```bash
# prerequisite: the Gemini CLI, installed and logged in
npm install -g @google/gemini-cli && gemini login

git clone --depth 1 https://github.com/arielfikru/claude-ask-gemini.git
bash claude-ask-gemini/install.sh
ask-gemini -f some-image.png "what is in this image?"
```

## What gets installed

| Path | What |
| ---- | ---- |
| `~/.claude/bin/ask-gemini` | the CLI (stdlib Python, zero deps) |
| `~/.claude/bin/ask-gemini-batch` | parallel fan-out over many media/questions |
| `~/.claude/skills/gemini/SKILL.md` | the `/gemini` skill: when/how the agent delegates |
| `~/.claude/mcp/gemini-server.py` | optional MCP wrapper (typed tools) |
| `~/.bashrc` (+`~/.zshrc`) | adds `~/.claude/bin` to PATH |

## CLI usage

```bash
ask-gemini -f screenshot.png "what UI bug is visible? be specific"
ask-gemini -f clip.mp4 "summarize what happens, with rough timestamps"
ask-gemini -f before.png -f after.png "what changed between these two?"
cat spec.md | ask-gemini -f mockup.png "does this mockup match the spec?"
ask-gemini "explain the CAP theorem in 3 sentences"   # plain text works too
```

| Flag | Meaning |
| ---- | ------- |
| `-f FILE` | media/file to analyze (image, video, doc); **repeatable** |
| `--flash` | fast/cheap model (`gemini-3-flash-preview`) |
| `--pro` | most capable model (`gemini-3.1-pro-preview`, the default) |
| `-m MODEL` | explicit Gemini model name |
| `-c N` | self-consistency: sample N, majority-vote (see below) |
| `--timeout N` | seconds before giving up (default 300, env `GEMINI_TIMEOUT`) |
| `--raw` | print the full Gemini JSON, not just `.response` |
| `-q` | suppress the usage line on stderr |

Prompt comes from args and/or piped stdin. Media is referenced by Gemini's
native multimodal read — no OCR/transcoding step.

### Picking the model

Default is **pro** — best for tricky reads (subtle UI bugs, dense diagrams,
fine detail). Use `--flash` for bulk or simple reads (obvious content, large
batches): faster and cheaper, and a sensible default for `ask-gemini-batch`.
`-m` takes any explicit model name (e.g. `gemini-2.5-flash`, `gemini-2.5-pro`).

```bash
ask-gemini --flash -f thumb.jpg "is there text in this image? yes/no"
ask-gemini --pro   -f dense-dashboard.png "list every chart and what it shows"
ask-gemini-batch --flash -p "any obvious layout bug?" shots/*.png -j 8
```

### Why it stays lean

The Gemini CLI auto-loads `GEMINI.md` and scans its working directory, which can
bloat a single call to ~90k input tokens. `ask-gemini` runs `gemini` from an
**empty temp dir** and copies each `-f` file into it (the CLI sandboxes file
reads to its cwd), so every call stays ~8k tokens — and media outside the
workspace still works. Don't call `gemini` directly for analysis; you lose both
the lean cwd and the media sandboxing.

## Self-consistency voting

`-c N` samples the same question N times in parallel and majority-votes the
answer, flagging low agreement. It **only helps for discrete answers** — counts,
yes/no, OCR'd text, classification — and is useless for open-ended description
(every phrasing differs, so there's no majority).

```bash
ask-gemini -f crowd.jpg -c 5 "how many people? put the number on the last line"
# stderr: [gemini-3.1-pro-preview | ...] | agreement 4/5
```

Agreement of `≤ N/2` is tagged `⚠ LOW — verify`.

## Batch fan-out

`ask-gemini-batch` runs many analysis calls in parallel (each through
`ask-gemini`, so every worker stays lean). Two modes, picked by input:

```bash
# mode 1 — same prompt over many media files (positional)
ask-gemini-batch -p "what UI bug is visible?" shots/*.png -j 8

# mode 2 — many questions, one shared media file (prompts on stdin)
printf 'what shape?\nwhat color?\n' | ask-gemini-batch -c diagram.png
ask-gemini-batch -c clip.mp4 --delimiter '---' < prompts.txt
```

| Flag | Meaning |
| ---- | ------- |
| `-p PROMPT` | shared question applied to each file (mode 1) |
| `-c FILE` | shared media file for stdin prompts (mode 2) |
| `-d STR` | split stdin prompts on this delimiter line (else one per line) |
| `-j N` | parallel workers (default 4) |
| `-m MODEL` / `--timeout N` | applied to every call |
| `--json` | emit a JSON array of `{index, label, output, ok}` |

## MCP (optional)

`mcp/server.py` is a thin [FastMCP](https://github.com/modelcontextprotocol/python-sdk)
wrapper exposing `ask_gemini` and `ask_gemini_batch` as typed tools that shell
out to the same CLIs. Register it so MCP-native agents can call Gemini without
composing a Bash command:

```bash
pip install 'mcp>=1.2.0'
claude mcp add -s user gemini -- python3 ~/.claude/mcp/gemini-server.py
```

The CLI stays the source of truth (lean cwd, media staging, voting all live
there); the MCP server adds nothing but ergonomics.

## When to delegate to Gemini

- Reading a screenshot / photo / scan and answering questions about it
- Spotting visual bugs, layout issues, UI/UX problems in an image
- Describing or summarizing a video clip, extracting on-screen text
- Comparing two images (before/after, design vs implementation)
- OCR-ish extraction when no dedicated OCR is set up

…and **not** for image generation, pure-text work (use a text model), or
correctness-critical final calls (the senior reviews, never ships blind).

## Requirements

- The [Gemini CLI](https://github.com/google-gemini/gemini-cli), installed and
  logged in (`gemini login`)
- Python 3.8+ (stdlib only for the CLIs — no pip installs)
- Optional: `mcp>=1.2.0` for the MCP server; Claude Code for the `/gemini` skill

## License

MIT
