#!/usr/bin/env python3
"""ask-gemini — call Gemini CLI headless for image/video/file analysis. Stdlib only.

Gemini is the "vision intern": hand it media + a question, get an answer back.
Wraps `gemini -p ... --skip-trust -o json` and parses the `.response` field.
Media files are injected into the prompt via Gemini's `@path` syntax.

Usage:
  ask-gemini "explain quicksort"                       # plain text question
  ask-gemini -f shot.png "what UI bug is visible?"     # analyze an image
  ask-gemini -f clip.mp4 "summarize what happens"      # analyze a video
  ask-gemini -f a.png -f b.png "compare these two"     # multiple media
  echo "long text" | ask-gemini "summarize this"       # stdin appended

Why a clean cwd: Gemini auto-loads GEMINI.md + scans the working dir, which
bloats input tokens. This wrapper runs gemini from an empty temp dir so each
call stays lean (~8k tokens base instead of ~90k).

Env:
  GEMINI_MODEL   optional, overrides default model

Exit codes: 0 ok, 1 usage/input error, 2 gemini error.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile

DEFAULT_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "300"))

# Model shortcuts. Pro = most capable (default); flash = faster/cheaper.
MODEL_PRO = "gemini-3.1-pro-preview"
MODEL_FLASH = "gemini-3-flash-preview"


def die(msg, code):
    print(f"ask-gemini: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_args():
    p = argparse.ArgumentParser(add_help=True, description="Call Gemini CLI headless for analysis.")
    p.add_argument("prompt", nargs="*", help="prompt text (else/also read stdin)")
    p.add_argument("--file", "-f", action="append", default=[],
                   help="media/file to analyze (image, video, doc); repeatable")
    p.add_argument("--model", "-m", help="explicit Gemini model name")
    p.add_argument("--flash", action="store_true",
                   help=f"shortcut for the fast/cheap model ({MODEL_FLASH})")
    p.add_argument("--pro", action="store_true",
                   help=f"shortcut for the most capable model ({MODEL_PRO})")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"seconds before giving up (default {DEFAULT_TIMEOUT}, env GEMINI_TIMEOUT)")
    p.add_argument("--consistency", "-c", type=int, metavar="N",
                   help="self-consistency: sample N, majority-vote the answer, flag disagreement"
                        " (only useful for discrete answers: counts, yes/no, OCR, classification)")
    p.add_argument("--raw", action="store_true", help="print full gemini JSON, not just .response")
    p.add_argument("--quiet", "-q", action="store_true", help="suppress usage stats on stderr")
    return p.parse_args()


def build_prompt(args):
    parts = []
    if args.prompt:
        parts.append(" ".join(args.prompt))
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            parts.append(piped)
    text = " ".join(parts).strip()
    if not text and not args.file:
        die("empty prompt (pass args, --file, or pipe stdin)", 1)
    return text


def resolve_files(paths):
    out = []
    for path in paths:
        ap = os.path.abspath(path)
        if not os.path.exists(ap):
            die(f"file not found: {path}", 1)
        out.append(ap)
    return out


def resolve_model(args):
    """Explicit -m wins, then --flash/--pro shortcuts, then env, else gemini default."""
    if args.model:
        return args.model
    if args.flash:
        return MODEL_FLASH
    if args.pro:
        return MODEL_PRO
    return os.environ.get("GEMINI_MODEL")


def build_cmd(args, prompt):
    cmd = ["gemini", "-p", prompt, "--skip-trust", "-o", "json"]
    model = resolve_model(args)
    if model:
        cmd += ["-m", model]
    return cmd


def stage_media(workdir, files):
    """Copy media into the workdir so gemini (sandboxed to cwd) can read them.
    Returns @basename refs, de-duplicating name collisions."""
    refs, used = [], {}
    for src in files:
        base = os.path.basename(src)
        if base in used:
            stem, ext = os.path.splitext(base)
            base = f"{stem}_{used[base]}{ext}"
        used[os.path.basename(src)] = used.get(os.path.basename(src), 0) + 1
        shutil.copy2(src, os.path.join(workdir, base))
        refs.append(f"@{base}")
    return refs


def run_gemini(args, prompt, files, timeout):
    # Run from an empty temp dir so gemini doesn't scan/load the real workspace.
    # Media is copied in and referenced relative, since gemini sandboxes reads to cwd.
    with tempfile.TemporaryDirectory(prefix="ask-gemini-") as workdir:
        refs = stage_media(workdir, files)
        full_prompt = (prompt + " " + " ".join(refs)).strip() if refs else prompt
        cmd = build_cmd(args, full_prompt)
        try:
            proc = subprocess.run(cmd, cwd=workdir, capture_output=True,
                                  text=True, timeout=timeout)
        except FileNotFoundError:
            die("gemini CLI not found on PATH", 2)
        except subprocess.TimeoutExpired:
            die(f"gemini timed out after {timeout}s", 2)
    if proc.returncode != 0:
        die(f"gemini exited {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}", 2)
    return proc.stdout


def parse_response(stdout):
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        die(f"unparseable gemini output: {stdout[:500]}", 2)
    return data


def analyze_once(args, prompt, files, timeout):
    """One Gemini call -> (response_text, parsed_json)."""
    data = parse_response(run_gemini(args, prompt, files, timeout))
    return data.get("response", ""), data


def format_usage(data):
    models = (data.get("stats") or {}).get("models") or {}
    if not models:
        return None
    name = next(iter(models))
    tok = models[name].get("tokens", {})
    return (f"[{name} | in {tok.get('input', '?')} out {tok.get('candidates', '?')} tok"
            f" | cached {tok.get('cached', 0)}]")


def vote_key(text):
    """Answer proxy for voting: normalized last non-empty line, alphanumeric."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    last = lines[-1] if lines else text
    return "".join(ch.lower() for ch in last if ch.isalnum())[:120]


def run_consistency(args, prompt, files, timeout, n):
    """Sample N times in parallel, majority-vote on the answer proxy."""
    def one(_):
        return analyze_once(args, prompt, files, timeout)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
        results = list(pool.map(one, range(n)))
    responses = [r for r, _ in results]
    keys = [vote_key(r) for r in responses]
    win_key, votes = collections.Counter(keys).most_common(1)[0]
    rep = next(r for r, k in zip(responses, keys) if k == win_key)
    return rep, votes, results[0][1]


def main():
    args = parse_args()
    prompt = build_prompt(args)
    files = resolve_files(args.file)
    n = args.consistency
    if n and n > 1:
        response, votes, data = run_consistency(args, prompt, files, args.timeout, n)
    else:
        response, data = analyze_once(args, prompt, files, args.timeout)
        votes = None
    if args.raw:
        print(json.dumps(data, indent=2))
    else:
        print(response)
    if not args.quiet:
        line = format_usage(data) or ""
        if votes is not None:
            agree = f"agreement {votes}/{n}" + ("  ⚠ LOW — verify" if votes * 2 <= n else "")
            line = f"{line} | {agree}" if line else f"[{agree}]"
        if line:
            print(line, file=sys.stderr)


if __name__ == "__main__":
    main()
