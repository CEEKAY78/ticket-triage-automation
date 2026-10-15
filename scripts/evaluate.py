"""Evaluate the classifier on the labelled synthetic tickets with a real local model.

    python scripts/evaluate.py [--model qwen2.5:7b-instruct] [--limit N]

Writes one JSON line per ticket to eval/runs/<model>.jsonl as soon as it is classified
(a rerun skips tickets already there) and prints/writes the summary to eval/<model>.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from triage.classify import classify, route  # noqa: E402
from triage.ollama import OllamaChat  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # torn last line after a crash
    return out


def summarise(rows: list[dict], model: str) -> str:
    n = len(rows)
    auto = [r for r in rows if r["queue"] == "auto"]
    acc = {f: sum(r[f"pred_{f}"] == r[f] for r in rows) / n
           for f in ("category", "urgency", "language")}
    auto_acc = sum(r["pred_category"] == r["category"] for r in auto) / len(auto) if auto else 0
    team_ok = sum(r["pred_team"] == r["team"] for r in auto) / len(auto) if auto else 0
    wrong = Counter((r["category"], r["pred_category"]) for r in rows
                    if r["pred_category"] != r["category"])
    lines = [
        f"# Evaluation: {model}, {n} synthetic tickets",
        "",
        "| metric | value |",
        "|---|---|",
        f"| category accuracy (all tickets) | {acc['category']:.1%} |",
        f"| urgency accuracy | {acc['urgency']:.1%} |",
        f"| language accuracy | {acc['language']:.1%} |",
        f"| automation rate (routed without a human) | {len(auto) / n:.1%} ({len(auto)}/{n}) |",
        f"| category accuracy of auto-routed tickets | {auto_acc:.1%} |",
        f"| correct team for auto-routed tickets | {team_ok:.1%} |",
        f"| sent to human review | {n - len(auto)} |",
        f"| median seconds per ticket | {statistics.median(r['seconds'] for r in rows):.1f} |",
        f"| personal data items masked | {sum(sum(r['pii_masked'].values()) for r in rows)} |",
        "",
        "Most frequent confusions (true -> predicted): "
        + (", ".join(f"{a} -> {b} ({c})" for (a, b), c in wrong.most_common(5)) or "none"),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    tickets = read_jsonl(ROOT / "data" / "tickets_labelled.jsonl")[: args.limit]
    slug = args.model.replace(":", "_").replace("/", "_")
    out = args.out or ROOT / "eval" / "runs" / f"{slug}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["ticket_id"]: r for r in read_jsonl(out)}
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in done.values()),
                   encoding="utf-8")
    llm = OllamaChat(args.model)
    from triage.classify import TEAM

    for t in tickets:
        if t["ticket_id"] in done:
            continue
        start = time.perf_counter()
        tri = classify(t["text"], llm)
        row = {
            "ticket_id": t["ticket_id"], "category": t["category"], "urgency": t["urgency"],
            "language": t["language"], "team": TEAM[t["category"]],
            "pred_category": tri.category, "pred_urgency": tri.urgency,
            "pred_language": tri.language, "pred_team": route(tri)[0],
            "confidence": tri.confidence, "queue": tri.queue, "attempts": tri.attempts,
            "review_reason": tri.review_reason, "pii_masked": tri.pii_masked,
            "seconds": round(time.perf_counter() - start, 2),
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        done[t["ticket_id"]] = row
    rows = [done[t["ticket_id"]] for t in tickets if t["ticket_id"] in done]
    text = summarise(rows, args.model)
    if args.limit is None:
        (ROOT / "eval" / f"{slug}.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
