#!/usr/bin/env python3
"""mock-3-judge.py: per-criterion LLM judge for APEX-Accounting style tasks.

Grades outputs against binary rubric criteria, one judge call per criterion,
the way the APEX-Accounting dataset card describes its judge: the judge sees
the task prompt, the criterion text and the final output only. It never sees
the trajectory, the gold answer or the context file list.

Usage
  python mock-3-judge.py --data dev.jsonl --outputs outputs.jsonl --out results/
  python mock-3-judge.py --data dev.jsonl --gold --out results/

  outputs.jsonl  one line per (task, run): {"task_id": str, "run": int, "output": str}
  --gold         grades each task's gold_output as run 0 (the calibration check)

Environment
  OPENAI_API_KEY   key for the OpenAI-compatible endpoint
  OPENAI_BASE_URL  endpoint base URL (default: the openai package default)
  JUDGE_MODEL      model name sent in every request
  JUDGE_FAKE=1     use the offline test stub instead of a model (see fake_judge)

Outputs, written under --out
  results.jsonl    one line per criterion judgement, raw judge text included
  metrics.json     per-task percent of criteria met, Mean Criteria@k, config

Requires Python 3.11+ and the openai package (imported only when JUDGE_FAKE is unset).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

JUDGE_TEMPERATURE = 0

SYSTEM_PROMPT = (
    "You are an expert evaluator grading an AI agent's final answer to an "
    "accounting task against one rubric criterion. Be precise, evidence-based "
    "and objective."
)


def build_user_prompt(task_prompt: str, criterion: str, output: str) -> str:
    """The Mercor-shaped judge prompt: task prompt, one criterion, final output."""
    return (
        "You are evaluating a model-generated response against a specific criterion.\n\n"
        "Task prompt given to the model:\n"
        f"<TASK_PROMPT>\n{task_prompt}\n</TASK_PROMPT>\n\n"
        "Criterion to evaluate:\n"
        f"<CRITERION>\n{criterion}\n</CRITERION>\n\n"
        "Response to evaluate:\n"
        f"<RESPONSE>\n{output}\n</RESPONSE>\n\n"
        "Instructions:\n"
        "1. Analyze the response against this criterion and nothing else. Do not "
        "penalize the response for anything the criterion does not ask for.\n"
        "2. Base the judgement only on what is written in the response. A claim "
        "that work was done is not evidence that it was done.\n"
        "3. Number formatting is not a difference: $29,700, 29,700, 29700 and "
        "$29,700.00 are the same value. When the criterion states an acceptable "
        "value or range, any value inside it meets the criterion and any value "
        "outside it does not.\n"
        "4. Every part of a compound criterion must be verified. If the response "
        "gives several conflicting answers where one was asked for, the criterion "
        "is not met.\n"
        "5. Determine if the response fully satisfies the criterion (result = 1) "
        "or not (result = 0).\n"
        "6. Provide a concise explanation (maximum 2-3 sentences).\n\n"
        "Return only a JSON object of the form "
        '{"result": <1 or 0>, "reason": "<concise explanation>"}'
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Job:
    task_index: int
    task_id: str
    task_name: str
    run: int
    prompt: str
    output: str
    criterion_index: int
    criterion_id: str
    criterion_type: str
    criterion: str


def read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: bad JSON ({exc})")
    return rows


def load_tasks(path: str) -> list[dict]:
    tasks = read_jsonl(path)
    if not tasks:
        raise SystemExit(f"{path}: no tasks")
    for task in tasks:
        for key in ("task_id", "prompt", "rubric"):
            if key not in task:
                raise SystemExit(f"{path}: task without '{key}': {task.get('task_id', '?')}")
        if not task["rubric"]:
            raise SystemExit(f"{path}: {task['task_id']} has an empty rubric")
        for crit in task["rubric"]:
            for key in ("id", "description"):
                if key not in crit:
                    raise SystemExit(f"{path}: {task['task_id']} has a criterion without '{key}'")
    ids = [task["task_id"] for task in tasks]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{path}: duplicate task_id")
    return tasks


def load_outputs(path: str, tasks: list[dict]) -> list[dict]:
    known = {task["task_id"] for task in tasks}
    rows = read_jsonl(path)
    seen: set[tuple[str, int]] = set()
    for lineno, row in enumerate(rows, 1):
        run = row.get("run")
        if (
            not isinstance(row.get("task_id"), str)
            or not isinstance(row.get("output"), str)
            or isinstance(run, bool)
            or not isinstance(run, int)
        ):
            raise SystemExit(f"{path}:{lineno}: need string task_id, int run, string output")
        if row["task_id"] not in known:
            raise SystemExit(f"{path}:{lineno}: unknown task_id {row['task_id']}")
        key = (row["task_id"], run)
        if key in seen:
            raise SystemExit(f"{path}:{lineno}: duplicate (task_id, run) {key}")
        seen.add(key)
    return rows


def gold_outputs(tasks: list[dict]) -> list[dict]:
    """Wrap each task's gold_output as a run-0 output row, so --gold goes
    through the same pairing and judging path as --outputs."""
    rows = []
    for task in tasks:
        if not task.get("gold_output"):
            raise SystemExit(f"{task['task_id']} has no gold_output; cannot run --gold")
        rows.append({"task_id": task["task_id"], "run": 0, "output": task["gold_output"]})
    return rows


def build_jobs(tasks: list[dict], outputs: list[dict]) -> list[Job]:
    """One job per (output row, criterion of that row's task)."""
    by_id = {task["task_id"]: (index, task) for index, task in enumerate(tasks)}
    jobs = []
    for row in outputs:
        index, task = by_id[row["task_id"]]
        for c_index, crit in enumerate(task["rubric"]):
            jobs.append(
                Job(
                    task_index=index,
                    task_id=task["task_id"],
                    task_name=task.get("task_name", task["task_id"]),
                    run=row["run"],
                    prompt=task["prompt"],
                    output=row["output"],
                    criterion_index=c_index,
                    criterion_id=crit["id"],
                    criterion_type=crit.get("criterion_type", ""),
                    criterion=crit["description"],
                )
            )
    return jobs


# ---------------------------------------------------------------------------
# Judges
# ---------------------------------------------------------------------------

def make_client(timeout: float):
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("pip install openai, or set JUDGE_FAKE=1 for the offline stub")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")
    # max_retries=0: retries and backoff are handled in judge_job so that every
    # attempt's raw text is kept.
    return OpenAI(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        timeout=timeout,
        max_retries=0,
    )


def call_model(client, model: str, job: Job) -> str:
    response = client.chat.completions.create(
        model=model,
        temperature=JUDGE_TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(job.prompt, job.criterion, job.output)},
        ],
    )
    return response.choices[0].message.content or ""


# ---- offline test stub ------------------------------------------------------
# JUDGE_FAKE=1 swaps the model for fake_judge. It is a plumbing test stub, NOT
# a judge. It passes a criterion when every number written in the criterion
# text also appears in the output. Numbers are compared as digit strings:
# commas, currency signs and percent signs are ignored and trailing zeros after
# the decimal point are dropped, so "$29,700.00", "29,700" and "29700" are the
# same number. Numbers inside the criterion's "(acceptable value/range ...)"
# clause are not required, because they are the tolerance, not values an
# answer states: range bounds such as "$2,196.80 to $2,198.80" never appear in
# a correct answer. A criterion with no digits in it always passes. The stub
# cannot read sign, account names, reasoning or hedging, so its scores say
# nothing about how accurate a real judge is. Use it to test the pipeline.

NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
TOLERANCE_RE = re.compile(r"\((?:acceptable|Acceptable)[^)]*\)")


def normalize_number(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        whole, frac = token.split(".", 1)
        frac = frac.rstrip("0")
        token = whole + ("." + frac if frac else "")
    return token.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {normalize_number(m) for m in NUMBER_RE.findall(text)}


def fake_judge(criterion: str, output: str) -> str:
    required = numbers_in(TOLERANCE_RE.sub("", criterion))
    missing = sorted(required - numbers_in(output))
    if missing:
        verdict = {"result": 0, "reason": "stub: numbers missing from output: " + ", ".join(missing)}
    else:
        verdict = {"result": 1, "reason": "stub: every number in the criterion appears in the output"}
    return json.dumps(verdict)


# ---------------------------------------------------------------------------
# One judgement, with retries
# ---------------------------------------------------------------------------

def parse_judgement(text: str) -> tuple[int, str]:
    """Return (result, reason) from the judge text; raise ValueError if unusable."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in judge response")
    obj = json.loads(text[start : end + 1])
    result = obj.get("result")
    if isinstance(result, str) and result.strip() in ("0", "1"):
        result = int(result.strip())
    if isinstance(result, bool) or (isinstance(result, (int, float)) and result in (0, 1)):
        return int(result), str(obj.get("reason", ""))
    raise ValueError(f"result is not 0 or 1: {obj.get('result')!r}")


def judge_job(job: Job, judge_fn, max_retries: int, backoff_base: float = 1.0, backoff_cap: float = 30.0) -> dict:
    raw_attempts: list[str] = []  # every response text received, in order
    errors: list[str] = []  # one entry per failed call or unusable reply, in order
    calls = 0
    result, reason = None, ""
    for attempt in range(max_retries + 1):
        calls += 1
        try:
            raw = judge_fn(job)
            raw_attempts.append(raw)
            result, reason = parse_judgement(raw)
            break
        except Exception as exc:  # API errors and unusable replies both retry
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < max_retries:
                delay = min(backoff_cap, backoff_base * 2**attempt) * (0.5 + random.random())
                time.sleep(delay)
    record = asdict(job)
    record.update(
        {
            "result": result,  # None when every call failed; counted as not met
            "reason": reason,
            "raw_response": raw_attempts[-1] if raw_attempts else "",
            "raw_attempts": raw_attempts,
            "calls": calls,
            "errors": errors,
            "error": errors[-1] if result is None else None,
        }
    )
    return record


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def percentile(sorted_values: list[float], p: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_ci(values: list[float], resamples: int, seed: int = 0) -> list[float] | None:
    """Task-level bootstrap: resample tasks with replacement, recompute the mean."""
    if not values or resamples <= 0:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return [round(percentile(means, 2.5), 2), round(percentile(means, 97.5), 2)]


def compute_metrics(records: list[dict], tasks: list[dict], resamples: int) -> dict:
    n_criteria = {task["task_id"]: len(task["rubric"]) for task in tasks}
    names = {task["task_id"]: task.get("task_name", task["task_id"]) for task in tasks}
    met: dict[tuple[str, int], int] = defaultdict(int)
    judged: dict[tuple[str, int], int] = defaultdict(int)
    failures = 0
    for rec in records:
        key = (rec["task_id"], rec["run"])
        judged[key] += 1
        if rec["result"] == 1:
            met[key] += 1
        if rec["result"] is None:
            failures += 1  # unusable judge call: counted as not met

    per_task = []
    for task in tasks:
        tid = task["task_id"]
        runs = sorted(run for (task_id, run) in judged if task_id == tid)
        if not runs:
            continue
        run_pct = {run: 100.0 * met[(tid, run)] / n_criteria[tid] for run in runs}
        per_task.append(
            {
                "task_id": tid,
                "task_name": names[tid],
                "n_criteria": n_criteria[tid],
                "runs": {str(run): round(pct, 2) for run, pct in run_pct.items()},
                "mean_pct": round(statistics.fmean(run_pct.values()), 2),
            }
        )

    task_scores = [row["mean_pct"] for row in per_task]
    scored_ids = {row["task_id"] for row in per_task}
    runs_per_task = sorted({len(row["runs"]) for row in per_task})
    total_judged = sum(judged.values())
    total_met = sum(met.values())
    return {
        "k": runs_per_task[0] if runs_per_task else 0,
        "k_uniform_across_tasks": len(runs_per_task) <= 1,
        "runs_per_task_observed": runs_per_task,
        "n_tasks_scored": len(per_task),
        "n_tasks_in_data": len(tasks),
        "tasks_without_outputs": [task["task_id"] for task in tasks if task["task_id"] not in scored_ids],
        "mean_criteria_at_k": round(statistics.fmean(task_scores), 2) if task_scores else None,
        "mean_criteria_at_k_ci95_task_bootstrap": bootstrap_ci(task_scores, resamples),
        "bootstrap_resamples": resamples,
        "criteria_met_micro_pct": round(100.0 * total_met / total_judged, 2) if total_judged else None,
        "criteria_judged": total_judged,
        "criteria_met": total_met,
        "judge_failures_counted_as_not_met": failures,
        "per_task": per_task,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="tasks jsonl (dev.jsonl)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--outputs", help="model outputs jsonl: {task_id, run, output}")
    mode.add_argument("--gold", action="store_true", help="grade each task's gold_output as run 0")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--workers", type=int, default=8, help="concurrent judge calls (default 8)")
    ap.add_argument("--max-retries", type=int, default=5, help="retries per criterion (default 5)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per judge call (default 120)")
    ap.add_argument("--limit", type=int, default=None, help="judge only the first N tasks of --data")
    ap.add_argument("--bootstrap", type=int, default=2000, help="task-level bootstrap resamples (default 2000)")
    args = ap.parse_args()

    tasks = load_tasks(args.data)
    if args.gold:
        if args.limit:
            tasks = tasks[: args.limit]
        outputs = gold_outputs(tasks)
    else:
        outputs = load_outputs(args.outputs, tasks)
        if args.limit:
            tasks = tasks[: args.limit]
            keep = {task["task_id"] for task in tasks}
            outputs = [row for row in outputs if row["task_id"] in keep]
    jobs = build_jobs(tasks, outputs)

    fake = os.environ.get("JUDGE_FAKE") == "1"
    if fake:
        model = "fake-stub"
        judge_fn = lambda job: fake_judge(job.criterion, job.output)  # noqa: E731
    else:
        model = os.environ.get("JUDGE_MODEL")
        if not model:
            raise SystemExit("JUDGE_MODEL is not set")
        client = make_client(args.timeout)
        judge_fn = lambda job: call_model(client, model, job)  # noqa: E731

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"{len(tasks)} tasks, {len(outputs)} output rows, {len(jobs)} criterion judgements, "
        f"judge={'FAKE STUB' if fake else model}",
        file=sys.stderr,
    )

    started = time.time()
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(judge_job, job, judge_fn, args.max_retries) for job in jobs]
        for done, future in enumerate(as_completed(futures), 1):
            records.append(future.result())
            if done % 25 == 0 or done == len(futures):
                print(f"  judged {done}/{len(futures)}", file=sys.stderr)
    elapsed = time.time() - started
    records.sort(key=lambda rec: (rec["task_index"], rec["run"], rec["criterion_index"]))

    with open(out_dir / "results.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    metrics = compute_metrics(records, tasks, args.bootstrap)
    metrics["judge"] = {
        "mode": "gold" if args.gold else "outputs",
        "fake_stub": fake,
        "model": model,
        "base_url": None if fake else (os.environ.get("OPENAI_BASE_URL") or "openai default"),
        "temperature": JUDGE_TEMPERATURE,
        "max_retries": args.max_retries,
        "workers": args.workers,
        "data": args.data,
        "outputs": args.outputs,
        "limit": args.limit,
        "criterion_calls": len(jobs),
        "elapsed_seconds": round(elapsed, 1),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2, ensure_ascii=False)

    print(f"\n{'task':<18}{'criteria':>9}{'runs':>6}{'mean % met':>12}")
    for row in metrics["per_task"]:
        print(f"{row['task_name']:<18}{row['n_criteria']:>9}{len(row['runs']):>6}{row['mean_pct']:>12.1f}")
    ci = metrics["mean_criteria_at_k_ci95_task_bootstrap"]
    ci_text = f" (95% CI {ci[0]} to {ci[1]}, task-level bootstrap)" if ci else ""
    if metrics["n_tasks_scored"] == 0:
        print("\nno task was scored: no output row matched a task in --data")
    else:
        print(
            f"\nMean Criteria@{metrics['k']} = {metrics['mean_criteria_at_k']}%{ci_text} over "
            f"{metrics['n_tasks_scored']} tasks; {metrics['criteria_met']}/{metrics['criteria_judged']} "
            f"criteria met; {metrics['judge_failures_counted_as_not_met']} judge failures counted as not met"
        )
    if fake:
        print("JUDGE_FAKE=1: these are test-stub numbers, not judge numbers.")
    print(f"wrote {out_dir / 'results.jsonl'} and {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
