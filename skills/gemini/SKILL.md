---
name: gemini
description: Delegate image/video/visual analysis to Gemini (gemini-3.1-pro) via the headless Gemini CLI. Use when a task needs to look at a screenshot, photo, diagram, UI mockup, video clip, or any media file and answer questions about it — something text-only models (Claude inline, DeepSeek) cannot do. Trigger when the user says "pakai gemini", "analisa gambar/video ini", "/gemini", or whenever a subtask requires actually seeing pixels/frames. Claude stays the orchestrator and validates output. NOT for image generation (Gemini CLI cannot generate AI images).
---

# Gemini visual-analysis delegation — the "eyes" intern

Claude = orchestrator/brain. Gemini = the **vision intern**: hand it media + a
precise question, it looks at the pixels/frames and answers. Claude decides what
to delegate, calls the tool, then **validates** the result before using it.

Gemini fills the one gap DeepSeek and inline-Claude can't: **actually seeing
images and video**. Model is `gemini-3.1-pro-preview` (native multimodal).

## Tool

`ask-gemini` (at `~/.claude/bin/ask-gemini`). Stdlib Python, no deps. Wraps the
`gemini` CLI headless (`-p ... --skip-trust -o json`) and prints `.response`.

```bash
# analyze an image
ask-gemini -f screenshot.png "what UI bug is visible? be specific"

# analyze a video clip
ask-gemini -f clip.mp4 "summarize what happens, with rough timestamps"

# multiple media at once (compare)
ask-gemini -f before.png -f after.png "what changed between these two?"

# media + piped text context
cat spec.md | ask-gemini -f mockup.png "does this mockup match the spec?"

# plain text question (no media) also works
ask-gemini "explain the CAP theorem in 3 sentences"
```

Flags: `-f FILE` (media to analyze; **repeatable** for multiple files),
`--flash` (fast/cheap model `gemini-3-flash-preview`), `--pro` (most capable
`gemini-3.1-pro-preview`, the default), `-m MODEL` (explicit model name),
`-c N` (self-consistency: sample N, majority-vote), `--timeout N` (seconds,
default 300, env `GEMINI_TIMEOUT`), `--raw` (full gemini JSON not just
`.response`), `-q` (no stats). Prompt comes from args and/or piped stdin.

### Picking the model

- Default (no flag) = pro: best for tricky reads (subtle UI bugs, dense
  diagrams, fine detail). Use `--pro` to force it.
- `--flash` for bulk / simple reads (obvious content, large batches) — faster
  and cheaper. Good default for `ask-gemini-batch` over many files.

### Self-consistency vote (`-c N`)

`-c N` samples N times and majority-votes the answer. Use it when the
**answer is a single short verifiable value AND being wrong is costly** (a
number, name, yes/no, classification, picked option). Decision rule:

- USE `-c` when: factual/numeric/categorical answer + you'd otherwise have to
  trust it blind (no cheap way to verify). The `agreement X/N` line tells you
  how much to trust it; `⚠ LOW` = don't.
- SKIP `-c` when: output is prose/code/a draft (every sample differs, vote is
  meaningless), OR you can verify the result yourself anyway (run it, check
  the repo), OR cost matters more than the extra confidence. It is N× the
  tokens — never the default.

```bash
# discrete question -> vote reduces flaky/hallucinated answers
ask-gemini -f crowd.jpg -c 5 "how many people? number on the last line"
```

Stderr reports `agreement V/N` (⚠ LOW flagged when ≤ half agree).

### Batch fan-out

`ask-gemini-batch` runs many analysis calls in parallel (each through
`ask-gemini`, so every worker stays lean). Two modes, picked by input:

```bash
# mode 1 — same prompt over many media files (positional)
ask-gemini-batch -p "what UI bug is visible?" shots/*.png -j 8

# mode 2 — many questions, one shared media file (prompts on stdin)
printf 'what shape?\nwhat color?\n' | ask-gemini-batch -c diagram.png
ask-gemini-batch -c clip.mp4 --delimiter '---' < prompts.txt
```

Batch flags: `-p PROMPT` (shared, mode 1), `-c FILE` (shared media, mode 2),
`-d DELIM`, `-j N` (workers, def 4), `-m MODEL`, `--timeout N` (per call, def 600),
`--json` (array of `{index, label, output, ok}`). Use it for bulk: scanning many
screenshots/frames, or asking several questions about one image/video.

### How it stays lean

Gemini auto-loads `GEMINI.md` + scans its working dir, which bloated input to
~90k tokens/call. `ask-gemini` runs gemini from an **empty temp dir** and copies
each `-f` file into it (gemini sandboxes file reads to cwd), so calls stay ~8k
tokens. Don't bypass the wrapper by calling `gemini` directly for analysis — you
lose the lean cwd and media sandboxing both.

## When to delegate to Gemini

- Reading a screenshot / photo / scan and answering questions about it
- Spotting visual bugs, layout issues, UI/UX problems in an image
- Describing or summarizing a video clip, extracting on-screen text
- Comparing two images (before/after, design vs implementation)
- OCR-ish extraction from an image when no dedicated OCR is set up
- Any "look at this and tell me X" where pixels/frames matter

## When NOT to delegate

- **Image generation** — Gemini CLI cannot generate AI images; it only draws
  primitives via code (Pillow). Don't use it for "buatkan gambar/ilustrasi".
- Pure text work with no media → use DeepSeek (`/deepseek`) — cheaper.
- Anything needing this repo's structure/tools/graph → keep on Claude.
- Final correctness-critical calls → Claude reviews Gemini output, never blind.

## Pattern (intern protocol)

1. **Brief** — precise question. Gemini sees only the media you pass; state
   exactly what to look for.
2. **Assign** — `ask-gemini -f <media> "<question>"`. Pass multiple `-f` to
   compare. Bump `--timeout` for long videos.
3. **Review (mandatory)** — Gemini can misread fine detail and hallucinate.
   Spot-check claims; for anything important, re-open the image yourself or
   re-ask with a sharper prompt.
4. **Integrate** — use the validated answer; say Gemini produced the read.

## MCP (optional)

A thin MCP wrapper exists at `~/.claude/mcp/gemini-server.py` (registered as the
`gemini` MCP server, user scope). It exposes `ask_gemini` and `ask_gemini_batch`
as typed tools that shell out to these same CLIs — use it to call Gemini without
composing a Bash command. The CLI remains the source of truth (lean cwd, media
staging, voting all live there); the MCP server adds nothing but ergonomics.

## Notes

- Auth is OAuth-personal (already logged in). If calls 401, re-run `gemini login`.
- Supported media: common image formats (png/jpg/webp/…) and video (mp4/…). Large
  videos cost more tokens and time — raise `--timeout`.
- Related: [[reference-deepseek-delegation]] (text intern), same senior/intern
  review discipline applies here.
