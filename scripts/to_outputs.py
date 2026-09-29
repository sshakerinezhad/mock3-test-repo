"""TO OUTPUTS. results/apex_acc_v1/raw.jsonl -> outputs_<model>.jsonl per model for mock-3-judge.py --outputs.

    python scripts/to_outputs.py [RAW]

Line = {"task_id", "run": sample_index + 1, "output": response}. One file per model because the judge keys on
(task_id, run) and has no model field. raw.jsonl is append-only, so the last line per (model, task, sample) wins
(a rerun must not become a duplicate the judge rejects). Rows with no response are skipped and counted: that task
is then judged on fewer runs than the others (the judge reports k_uniform_across_tasks: false).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

raw = Path(sys.argv[1] if len(sys.argv) > 1 else "results/apex_acc_v1/raw.jsonl")
last: dict[tuple[str, str, int], dict] = {}
for line in raw.read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        last[(row["model"], row["task_id"], row["sample_index"])] = row

for model in sorted({m for m, _, _ in last}):
    keys = sorted(k for k in last if k[0] == model)
    ok = [last[k] for k in keys if isinstance(last[k]["response"], str)]
    skipped = [k[1:] for k in keys if not isinstance(last[k]["response"], str)]
    out = raw.parent / f"outputs_{model.rsplit('-', 1)[-1]}.jsonl"  # gpt-5.6-luna -> outputs_luna.jsonl
    out.write_text("".join(json.dumps({"task_id": r["task_id"], "run": r["sample_index"] + 1, "output": r["response"]},
                                      ensure_ascii=False) + "\n" for r in ok), encoding="utf-8")
    print(f"{model}: wrote {len(ok)} -> {out}; skipped {len(skipped)} with an error" + (f": {skipped}" if skipped else ""))
