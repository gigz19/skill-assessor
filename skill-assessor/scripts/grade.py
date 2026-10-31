#!/usr/bin/env python3
"""Grade a run's output folder against pass/fail criteria that were written BEFORE the run.

Usage: grade.py <criteria.json> <outputs_dir> [--json result.json]

criteria.json looks like:
  {"criteria": [
     {"id": "C1", "description": "report names all 3 planted bugs", "type": "contains",
      "file": "report.md", "text": ["off-by-one", "race", "leak"], "ignore_case": true},
     {"id": "C2", "description": "no stray files", "type": "only_files", "allowed": ["report.md"]},
     {"id": "C3", "description": "tone is neutral", "type": "manual", "rubric": "No blame language."}
  ]}

Types:
  file_exists   path
  contains      file, text (string or list; all must appear), ignore_case?
  not_contains  file, text (string or list; none may appear), ignore_case?
  regex         file, pattern, min? (default 1), max?   -> number of matches
  json_value    file, path (dot notation), equals? | min? | max?
  max_lines     file, max
  only_files    allowed (list of globs relative to outputs_dir)  -> catches side effects
  manual        rubric -> listed for the assessor to score by hand (never auto-passed)

Only text and JSON are read; nothing in the outputs is executed. For checks this list
cannot express, write your own small checker in the work folder (your code, never code
taken from the skill under review).
"""
import fnmatch
import json
import re
import signal
import sys
from pathlib import Path


def resolve(base: Path, rel: str):
    p = (base / rel).resolve()
    return p if base.resolve() in p.parents or p == base.resolve() else None


def read(base: Path, rel: str):
    p = resolve(base, rel)
    if p is None or not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def as_list(v):
    return v if isinstance(v, list) else [v]


def check(c: dict, base: Path):
    t = c.get("type")
    if t == "manual":
        return None, "needs manual scoring: " + c.get("rubric", "")
    if t == "only_files":
        allowed = c.get("allowed", [])
        found = [str(p.relative_to(base)) for p in base.rglob("*") if p.is_file()]
        stray = [f for f in found if not any(fnmatch.fnmatch(f, g) for g in allowed)]
        return not stray, f"stray files: {stray}" if stray else f"{len(found)} file(s), all allowed"
    if t == "file_exists":
        p = resolve(base, c["path"])
        return bool(p and p.exists()), c["path"]
    text = read(base, c["file"])
    if text is None:
        return False, f"missing file: {c['file']}"
    if t in ("contains", "not_contains"):
        hay = text.lower() if c.get("ignore_case") else text
        needles = [n.lower() if c.get("ignore_case") else n for n in as_list(c["text"])]
        present = [n for n in needles if n in hay]
        if t == "contains":
            missing = [n for n in needles if n not in hay]
            return not missing, f"missing: {missing}" if missing else "all present"
        return not present, f"found forbidden: {present}" if present else "none found"
    if t == "regex":
        n = len(re.findall(c["pattern"], text, re.M))
        lo, hi = c.get("min", 1), c.get("max")
        return n >= lo and (hi is None or n <= hi), f"{n} match(es)"
    if t == "max_lines":
        n = len(text.splitlines())
        return n <= c["max"], f"{n} lines"
    if t == "json_value":
        try:
            node = json.loads(text)
            for key in c["path"].split("."):
                node = node[int(key)] if isinstance(node, list) else node[key]
        except Exception as e:
            return False, f"cannot read {c['path']}: {e}"
        ok = True
        if "equals" in c:
            ok = ok and node == c["equals"]
        if "min" in c:
            ok = ok and node >= c["min"]
        if "max" in c:
            ok = ok and node <= c["max"]
        return ok, f"value={node!r}"
    return False, f"unknown criterion type: {t}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    criteria = json.load(open(sys.argv[1], encoding="utf-8"))["criteria"]
    base = Path(sys.argv[2])
    results = []
    for c in criteria:
        ok, detail = check(c, base)
        results.append({"id": c.get("id"), "description": c.get("description"), "pass": ok, "detail": detail})
    auto = [r for r in results if r["pass"] is not None]
    passed = sum(1 for r in auto if r["pass"])
    manual = len(results) - len(auto)
    print(f"{base}: {passed}/{len(auto)} automatic criteria passed" + (f", {manual} manual pending" if manual else ""))
    for r in results:
        tag = "MANUAL" if r["pass"] is None else ("PASS" if r["pass"] else "FAIL")
        print(f"  {tag:6} {r['id']}: {r['description']}  [{r['detail']}]")
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"passed": passed, "automatic_total": len(auto), "manual_pending": manual, "results": results}, open(out, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):  # not available on Windows
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
