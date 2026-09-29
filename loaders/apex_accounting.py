"""APEX-Accounting dev.jsonl -> the toolkit's three input shapes, plus run.py raw.jsonl -> mock-3-judge outputs.

File format: one JSON object per line: task_id, task_name, world_id, prompt, context_files, rubric, gold_output, metadata.
context_files are bare filenames, each found exactly once under <root>/world/ or <root>/task_files/ (root = dev.jsonl's grandparent).
rubric is a list of {id, criterion_type, description}; there is no weight or dependency in the data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import attachments

FIELDS = {"task_id", "task_name", "world_id", "prompt", "context_files", "rubric", "gold_output", "metadata"}


def die(msg: str) -> NoReturn:
    raise SystemExit(f"ERROR: {msg}")


def _rows(path: str | Path) -> list[dict]:
    path = Path(path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        die(f"{path}: no rows")
    for n, r in enumerate(rows, 1):
        if set(r) != FIELDS:
            die(f"{path}:{n}: fields {sorted(r)} are not the APEX-Accounting set {sorted(FIELDS)}")
    ids = [r["task_id"] for r in rows]
    if len(set(ids)) != len(ids):
        die(f"{path}: duplicate task_id")
    return rows


def is_apex_accounting(path: str | Path) -> bool:
    """True when the first line has exactly this dataset's fields (how run.py and grade.py pick this loader)."""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
    try:
        return set(json.loads(first)) == FIELDS
    except (json.JSONDecodeError, TypeError):
        return False


def _file_index(root: Path) -> dict[str, Path]:
    """Bare filename -> path under world/ and task_files/. A name found twice is ambiguous -> die."""
    index: dict[str, Path] = {}
    for sub in ("world", "task_files"):
        for p in sorted((root / sub).rglob("*")):
            if p.is_file():
                if p.name in index:
                    die(f"{p.name} exists twice ({index[p.name]}, {p}); cannot tell which one a task means")
                index[p.name] = p
    return index


def tasks(path: str | Path, task_ids: list | None = None, max_chars: int = attachments.MAX_CHARS) -> list[dict]:
    """Runner tasks for run.py: {"id", "prompt", "metadata"}; prompt = task prompt + one "=== <file> ===" block per file."""
    path = Path(path)
    rows = _rows(path)
    if task_ids is not None:
        unknown = [i for i in task_ids if i not in {r["task_id"] for r in rows}]
        if unknown:
            die(f"{path}: task_ids not found: {unknown}")
        rows = [r for r in rows if r["task_id"] in task_ids]  # filter BEFORE reading files: dropped tasks may be huge
    index = _file_index(path.parent.parent)
    out = []
    for r in rows:
        parts, chars = [r["prompt"]], {}
        if r["context_files"]:
            parts.append("==== Attached files content: ====")
        for name in r["context_files"]:
            if name not in index:
                die(f"task {r['task_id']}: context file {name} not found under world/ or task_files/")
            try:
                text = attachments.read_attachment(index[name], max_chars)  # unknown type or over the cap -> die
            except SystemExit as e:
                die(f"task {r['task_id']}: {str(e).removeprefix('ERROR: ')}")
            chars[name] = len(text)
            parts.append(f"=== {name} ===\n{text}")
        meta = {k: v for k, v in r.items() if k not in ("task_id", "prompt")}
        # prompt_raw: grade.py shows the judge the prompt without attachments; attachment_chars: run.py's dashboard
        meta.update(prompt_raw=r["prompt"], attachment_chars=chars)
        out.append({"id": r["task_id"], "prompt": "\n\n".join(parts), "metadata": meta})
    return out


def rubrics(path: str | Path) -> dict[str, list[dict]]:
    """Rubrics for grade.py: {task_id: [{"id", "description", "weight", "depends_on", "metadata"}]} in rubric order."""
    return {r["task_id"]: [{"id": c["id"], "description": c["description"],
                            "weight": c.get("weight"), "depends_on": c.get("depends_on"),
                            "metadata": {k: v for k, v in c.items() if k not in ("id", "description")}}
                           for c in r["rubric"]]
            for r in _rows(path)}


def gold(path: str | Path) -> dict[str, str]:
    """Reference answers: {task_id: gold_output}."""
    return {r["task_id"]: r["gold_output"] for r in _rows(path)}


def outputs(raw: str | Path, model: str) -> list[dict]:
    """run.py raw.jsonl -> [{"task_id", "run", "output"}] for ONE model (the judge's outputs file has no model field).

    Later lines win (appended reruns). A missing response is not turned into "" -> die, so it gets rerun, not scored 0.
    """
    raw = Path(raw)
    last: dict[tuple[str, int], dict] = {}
    for line in raw.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["model"] == model:
                last[(row["task_id"], row.get("sample_index", 0))] = row
    if not last:
        models = sorted({json.loads(l)["model"] for l in raw.read_text(encoding="utf-8").splitlines() if l.strip()})
        die(f"{raw}: no rows for model {model!r}; models present: {models}")
    empty = [k for k, row in last.items() if not isinstance(row.get("response"), str)]
    if empty:
        die(f"{raw}: {len(empty)} (task, sample) with no response for {model}, e.g. {sorted(empty)[:5]}; rerun them")
    return [{"task_id": t, "run": i, "output": last[(t, i)]["response"]} for t, i in sorted(last)]


if __name__ == "__main__":  # python -m loaders.apex_accounting RAW MODEL OUT  -> outputs.jsonl for mock-3-judge.py
    import sys
    if len(sys.argv) != 4:
        die("usage: python -m loaders.apex_accounting RAW MODEL OUT")
    rows = outputs(sys.argv[1], sys.argv[2])
    Path(sys.argv[3]).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(rows)} output row(s) -> {sys.argv[3]}")
