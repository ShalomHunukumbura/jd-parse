"""The command line: `jd-parse sample`, `label`, `extract`, `score`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import extract, label, score
from .providers import make_provider
from .sample import draw, read_jsonl, write_postings

DATA = Path("data")
POSTINGS = DATA / "postings.jsonl"
LABELS = DATA / "labels.jsonl"
RUNS = DATA / "runs"


def load_env(path: Path = Path(".env")) -> None:
    """Read KEY=value lines from .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


def postings_in(split: str) -> list[dict]:
    postings = read_jsonl(POSTINGS)
    if not postings:
        raise SystemExit(f"no postings yet: run `jd-parse sample` first ({POSTINGS})")
    return postings if split == "all" else [p for p in postings if p["split"] == split]


def cmd_sample(args: argparse.Namespace) -> None:
    url = os.environ.get("UNLISTED_DATABASE_URL")
    if not url:
        raise SystemExit("set UNLISTED_DATABASE_URL to Unlisted's Postgres (see .env.example)")
    if POSTINGS.exists() and not args.force:
        raise SystemExit(f"{POSTINGS} exists; --force replaces it (labels are kept)")
    postings = draw(url, args.per_bucket, args.test_share, args.seed)
    write_postings(POSTINGS, postings)
    by_bucket: dict[str, int] = {}
    for p in postings:
        by_bucket[p["bucket"]] = by_bucket.get(p["bucket"], 0) + 1
    tests = sum(p["split"] == "test" for p in postings)
    print(f"{len(postings)} postings ({len(postings) - tests} dev, {tests} test): {by_bucket}")


def cmd_label(args: argparse.Namespace) -> None:
    label.run(postings_in(args.split), LABELS, relabel=args.relabel)


def cmd_extract(args: argparse.Namespace) -> None:
    provider = make_provider(args.model)
    extract.run(provider, Path(args.prompt), postings_in(args.split), RUNS, args.limit)


def cmd_score(args: argparse.Namespace) -> None:
    postings = postings_in(args.split)
    ids = {p["id"] for p in postings}
    labels = {i: row["fields"] for i, row in label.load_labels(LABELS).items() if i in ids}
    if not labels:
        raise SystemExit(f"no labels for the {args.split} split yet: run `jd-parse label`")
    runs = args.runs or ["rules"] + sorted(p.name for p in RUNS.glob("*") if p.is_dir())
    scores = {}
    for name in runs:
        predictions = (
            score.rules_predictions(postings)
            if name == "rules"
            else score.load_predictions(RUNS / name)
        )
        scores[name] = score.score_run(labels, predictions)
    print(f"{len(labels)} labelled postings, {args.split} split\n")
    print(score.table(scores))


def main(argv: list[str] | None = None) -> None:
    load_env()
    parser = argparse.ArgumentParser(prog="jd-parse", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="draw postings to label from Unlisted's database")
    p.add_argument("--per-bucket", type=int, default=20)
    p.add_argument("--test-share", type=float, default=0.3)
    p.add_argument("--seed", default="jd-parse-1")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("label", help="hand-label postings in the terminal")
    p.add_argument("--split", choices=["dev", "test", "all"], default="all")
    p.add_argument("--relabel", action="store_true", help="go over labelled postings again")
    p.set_defaults(func=cmd_label)

    p = sub.add_parser("extract", help="run a prompt and model over the postings")
    p.add_argument("model", help="provider:model, e.g. ollama:qwen2.5:3b")
    p.add_argument("--prompt", default="prompts/v1.md")
    p.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    p.add_argument("--limit", type=int, help="stop after this many postings")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("score", help="compare runs with the labels")
    p.add_argument("runs", nargs="*", help="run folders under data/runs, or 'rules'")
    p.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    p.set_defaults(func=cmd_score)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
