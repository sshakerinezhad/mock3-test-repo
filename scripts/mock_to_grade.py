"""MOCK TO GRADE. mock-3-judge.py results (v1 + v1b rerun) -> the files `grade.py score` reads, one folder per judge.

    python scripts/mock_to_grade.py

For each judge (gemini, gpt41): concatenate results/judge_v1_{judge}_{luna,sol}/results.jsonl and
results/judge_v1b_{judge}_{luna,sol}/results.jsonl, check 267 rows per model (89 criteria x 3 runs), 534 per judge,
no duplicate (model, task_id, run, criterion_id), then write results/final_{judge}/tasks.jsonl (one judge call per row,
the shape grade.py build writes) and raw.jsonl (the shape run.py writes for those calls). The verdict goes in as
{"is_criteria_true", "rationale"}, the reply parse_verdict reads; a null result keeps the judge's raw text (or None
with its error) so grade.py counts it as a judge error, not as met. sample_index = run - 1 (runs are 1..3).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for grade
import grade

JUDGES = ("gemini", "gpt41")
MODELS = ("luna", "sol")
PER_MODEL = 267


def rows_for(judge: str, model: str) -> list[dict]:
    rows = []
    for stage in ("v1", "v1b"):
        path = Path(f"results/judge_{stage}_{judge}_{model}/results.jsonl")
        rows += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def convert(judge: str) -> None:
    tasks, raw, seen = [], [], set()
    for model in MODELS:
        rows = rows_for(judge, model)
        if len(rows) != PER_MODEL:
            grade.die(f"{judge}/{model}: {len(rows)} rows, expected {PER_MODEL}")
        for r in rows:
            key = (model, r["task_id"], r["run"], r["criterion_id"])
            if key in seen:
                grade.die(f"{judge}: duplicate {key}")
            seen.add(key)
            meta = {"task_id": r["task_id"], "model": model, "sample_index": r["run"] - 1, "criterion_id": r["criterion_id"]}
            jid = f"{r['task_id']}|{model}|{r['run'] - 1}|{r['criterion_id']}"
            tasks.append({"id": jid, "prompt": grade.judge_message(f"(judged by mock-3-judge.py, {judge})", r["prompt"],
                                                                   r["output"], r["criterion"]), **meta})
            if r["result"] in (0, 1):
                response, errors = json.dumps({"rationale": r["reason"], "is_criteria_true": r["result"] == 1}), []
            else:  # judge error: keep what it said, never a verdict
                response = r.get("raw_response") if isinstance(r.get("raw_response"), str) else None
                errors = [{"type": "JudgeError", "message": str(r.get("error"))}]
            raw.append({"task_id": jid, "model": judge, "response": response, "errors": errors, "metadata": meta})
    out = Path(f"results/final_{judge}")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("tasks.jsonl", tasks), ("raw.jsonl", raw)):
        (out / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in data), encoding="utf-8")
    nulls = sum(x["errors"] != [] for x in raw)
    print(f"{judge}: {len(raw)} rows ({PER_MODEL} per model), {nulls} null results kept as errors -> {out}/")


if __name__ == "__main__":
    for j in JUDGES:
        convert(j)
