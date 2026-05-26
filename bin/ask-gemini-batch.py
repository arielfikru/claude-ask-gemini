#!/usr/bin/env python3
"""ask-gemini-batch — fan out many visual-analysis calls to Gemini in parallel.

Each call goes through `ask-gemini`, so every worker stays lean (empty temp cwd,
media copied in). Two modes:

  1. Media fan-out (positional files): same prompt applied to each file.
       ask-gemini-batch -p "what UI bug is visible?" shot1.png shot2.png ...
       ask-gemini-batch -p "describe the scene" frames/*.jpg -j 8

  2. Prompt fan-out (stdin): many questions, one shared media file.
       ask-gemini-batch -c clip.mp4 < questions.txt
       ask-gemini-batch -c diagram.png --delimiter '---' < prompts.txt

Pick mode by input: positional files -> mode 1; else read prompts from stdin.
Shared opts (-m, --timeout) apply to every call.
"""
import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

CLI = str(Path(__file__).resolve().parent / "ask-gemini")


def parse_args():
    p = argparse.ArgumentParser(description="Fan out Gemini analysis in parallel.")
    p.add_argument("files", nargs="*", help="media files to fan out over (mode 1)")
    p.add_argument("--prompt", "-p", help="shared question applied to each file (mode 1)")
    p.add_argument("--context", "-c", help="shared media file for stdin prompts (mode 2)")
    p.add_argument("--delimiter", "-d", help="split stdin prompts on this line (else one per line)")
    p.add_argument("--jobs", "-j", type=int, default=4, help="parallel workers (default 4)")
    p.add_argument("--model", "-m", help="explicit model for all calls")
    p.add_argument("--flash", action="store_true", help="use the fast/cheap model for all")
    p.add_argument("--pro", action="store_true", help="use the most capable model for all")
    p.add_argument("--timeout", type=int, help="per-call timeout seconds (env GEMINI_TIMEOUT)")
    p.add_argument("--json", action="store_true", help="emit JSON array of results")
    return p.parse_args()


def die(msg, code=1):
    print(f"ask-gemini-batch: {msg}", file=sys.stderr)
    sys.exit(code)


def read_prompts(delimiter):
    raw = sys.stdin.read()
    chunks = raw.split(delimiter) if delimiter else raw.splitlines()
    prompts = [c.strip() for c in chunks if c.strip()]
    if not prompts:
        die("no prompts on stdin", 1)
    return prompts


def shared_flags(args, timeout):
    flags = ["-q", "--timeout", str(timeout)]
    if args.model:
        flags += ["-m", args.model]
    elif args.flash:
        flags.append("--flash")
    elif args.pro:
        flags.append("--pro")
    return flags


def build_jobs(args):
    """Return (label, cli_args) tuples. Mode 1 = files, mode 2 = stdin prompts."""
    if args.files:
        if not args.prompt:
            die("mode 1 needs --prompt to apply to each file", 1)
        return [(f, ["-f", f, args.prompt]) for f in args.files]
    prompts = read_prompts(args.delimiter)
    ctx = ["-f", args.context] if args.context else []
    return [(p[:60].replace("\n", " "), [*ctx, p]) for p in prompts]


def run_one(index, label, call_args, flags, timeout):
    try:
        proc = subprocess.run([CLI, *flags, *call_args], capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"index": index, "label": label, "output": "ERROR: timeout", "ok": False}
    if proc.returncode != 0:
        return {"index": index, "label": label,
                "output": f"ERROR: {proc.stderr.strip()}", "ok": False}
    return {"index": index, "label": label, "output": proc.stdout.rstrip("\n"), "ok": True}


def run_batch(jobs, flags, workers, timeout):
    results = [None] * len(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run_one, i, lbl, ca, flags, timeout): i
                for i, (lbl, ca) in enumerate(jobs)}
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results[r["index"]] = r
    return results


def emit(results, as_json):
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for r in results:
        print(f"=== [{r['index']}] {r['label']} ===")
        print(r["output"])
        print()


def main():
    args = parse_args()
    # A generous default timeout: batch jobs often include videos.
    timeout = args.timeout if args.timeout is not None else 600
    jobs = build_jobs(args)
    # Give the subprocess wrapper a little slack over gemini's own timeout.
    results = run_batch(jobs, shared_flags(args, timeout), args.jobs, timeout + 30)
    emit(results, args.json)
    if any(not r["ok"] for r in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
