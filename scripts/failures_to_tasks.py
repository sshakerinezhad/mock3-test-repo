"""FAILURES TO TASKS. Judge results (result 0 rows) -> run.py task JSONL for the failure classifier.

    python scripts/failures_to_tasks.py

Reads results/judge_v1_gemini_{luna,sol}/results.jsonl, writes results/classify/tasks.jsonl, one line per failed
criterion. Prompt = prompts/classify_criteria.md (provenance header stripped, as classifier.py does) + the criterion,
the judge's reason and the model's response, each under its own heading.

Fields besides id and prompt sit at the top level because run.py puts every such field into metadata itself
(a nested "metadata" key would arrive as metadata.metadata). trajectory_id, variant and categories are the fields
classifier.py score requires; variant = model, so score prints one column per model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classifier import categories, load_prompt  # noqa: E402

PROMPT = "prompts/classify_criteria.md"
SOURCES = {"luna": "results/judge_v1_gemini_luna/results.jsonl",
           "sol": "results/judge_v1_gemini_sol/results.jsonl"}
OUT = Path("results/classify/tasks.jsonl")

prompt = load_prompt(PROMPT)
cats = categories(prompt)
rows = []
for model, path in SOURCES.items():
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["result"] != 0:
            continue
        rid = f"{model}|{r['task_id']}|{r['run']}|{r['criterion_id']}"
        body = (f"## Criterion\n{r['criterion']}\n\n"
                f"## Judge's reason\n{r['reason']}\n\n"
                f"## Model response\n{r['output']}")
        rows.append({"id": rid, "prompt": prompt + "\n\n" + body,
                     "model": model, "task_name": r["task_name"], "run": r["run"],
                     "criterion_id": r["criterion_id"], "criterion_type": r["criterion_type"],
                     "trajectory_id": rid, "variant": model, "categories": cats})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
for model in SOURCES:
    print(f"  {model}: {sum(r['model'] == model for r in rows)}")
print(f"wrote {len(rows)} failures -> {OUT}")
