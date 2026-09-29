"""SAMPLE FAILURES. 20 random failures from results/classify/tasks.jsonl -> a blind hand-labelling sheet.

    python scripts/sample_failures.py

Writes results/classify/sample20.md (numbered; task, run, criterion, judge reason, response; no category) and
results/classify/labels.csv (columns n, category; empty). Fixed seed, so the same 20 come out every time.
Each item shows its id, which is the classifier's trajectory_id, so labels can be joined to its replies later.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 20
N = 20
DIR = Path("results/classify")

rows = [json.loads(line) for line in (DIR / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
sample = random.Random(SEED).sample(rows, N)

parts = [f"# Failure sample: {N} of {len(rows)} (seed {SEED})\n\n"
         "Label each one in labels.csv with a category from prompts/classify_criteria.md.\n"]
for n, r in enumerate(sample, 1):
    body = r["prompt"][r["prompt"].index("## Criterion"):]
    criterion, rest = body.removeprefix("## Criterion\n").split("\n\n## Judge's reason\n", 1)
    reason, response = rest.split("\n\n## Model response\n", 1)
    quoted = "\n".join("> " + line for line in response.splitlines())
    parts.append(f"\n---\n\n## {n}. {r['task_name']}, run {r['run']} ({r['model']})\n\n"
                 f"id: `{r['id']}`  \ncriterion type: {r['criterion_type']}\n\n"
                 f"**Criterion:** {criterion}\n\n**Judge's reason:** {reason}\n\n**Response:**\n\n{quoted}\n")

(DIR / "sample20.md").write_text("".join(parts), encoding="utf-8")
with (DIR / "labels.csv").open("w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows([["n", "category"]] + [[n, ""] for n in range(1, N + 1)])
print(f"wrote {DIR / 'sample20.md'} and {DIR / 'labels.csv'} ({N} of {len(rows)})")
