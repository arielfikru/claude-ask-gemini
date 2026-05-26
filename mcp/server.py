#!/usr/bin/env python3
"""Thin MCP wrapper over the ask-gemini CLI.

Optional adapter so MCP-native agents can delegate visual analysis to the
Gemini "eyes intern" without spawning a shell themselves. All real work
(lean temp-cwd, media staging, self-consistency vote, batch fan-out) lives in
the CLI — this just exposes it as typed MCP tools.

Run:  python3 gemini-server.py
Register (Claude Code):
  claude mcp add gemini -- python3 /abs/path/to/.claude/mcp/gemini-server.py
"""
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gemini")


def _cli(name):
    """Locate an installed CLI binary (PATH, then ~/.claude/bin)."""
    found = shutil.which(name)
    if found:
        return found
    fallback = Path.home() / ".claude" / "bin" / name
    if fallback.exists():
        return str(fallback)
    raise FileNotFoundError(f"{name} not found on PATH or ~/.claude/bin")


def _run(cmd, stdin=None):
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    out = proc.stdout.rstrip("\n")
    if proc.returncode != 0:
        return f"ERROR ({proc.returncode}): {proc.stderr.strip()}"
    return f"{out}\n\n[{proc.stderr.strip()}]" if proc.stderr.strip() else out


@mcp.tool()
def ask_gemini(
    prompt: str,
    files: list[str] | None = None,
    model: str = "",
    consistency: int = 0,
    timeout: int = 0,
) -> str:
    """Delegate one visual-analysis task to the Gemini intern.

    prompt: what to look for / answer. files: absolute paths to media (image,
      video, doc) to analyze — repeatable; Gemini sees only what you pass.
      model: explicit Gemini model name (else default). consistency: N>1 samples
      N and majority-votes the answer — ONLY useful for discrete answers
      (counts, yes/no, OCR, classification), useless for open-ended description.
      timeout: per-call seconds (0 = default 300; raise for long videos).
    NOT for image generation — Gemini CLI cannot generate AI images.
    Returns the answer; the trailing [..] line carries usage / agreement stats.
    """
    cmd = [_cli("ask-gemini")]
    for f in files or []:
        cmd += ["-f", f]
    if model:
        cmd += ["-m", model]
    if consistency and consistency > 1:
        cmd += ["-c", str(consistency)]
    if timeout:
        cmd += ["--timeout", str(timeout)]
    cmd.append(prompt)
    return _run(cmd)


@mcp.tool()
def ask_gemini_batch(
    prompt: str = "",
    files: list[str] | None = None,
    prompts: list[str] | None = None,
    context_file: str = "",
    model: str = "",
    jobs: int = 4,
    timeout: int = 0,
) -> str:
    """Fan out many Gemini analysis calls in parallel. Two modes:

    Mode 1 (media fan-out): pass `files` + a shared `prompt` — the prompt is
      applied to each file. Good for scanning many screenshots/frames.
    Mode 2 (prompt fan-out): pass `prompts` + one shared `context_file` media —
      each question asked about the same image/video.
    Returns JSON array of {index, label, output, ok}.
    """
    cmd = [_cli("ask-gemini-batch"), "--json", "-j", str(jobs)]
    if model:
        cmd += ["-m", model]
    if timeout:
        cmd += ["--timeout", str(timeout)]
    if files:
        cmd += ["-p", prompt, *files]
        return _run(cmd)
    if context_file:
        cmd += ["-c", context_file]
    return _run(cmd, stdin="\n".join(prompts or []) + "\n")


if __name__ == "__main__":
    mcp.run()
