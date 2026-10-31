#!/usr/bin/env python3
"""Inventory a skill folder without executing anything in it.

Usage: inventory.py <folder> [--pretty]

Reports, for every SKILL.md found under <folder>: parsed frontmatter, what loads
at each stage (metadata / body / referenced on-demand files; license text and
unreferenced files are counted separately because they are never loaded), rough token estimates,
files never mentioned in SKILL.md (orphans), hidden files, symlinks, and
binary files. Token counts are estimates (characters / 4), good for comparing
skills with each other, not for billing.
"""
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
KNOWN_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8000)
    except OSError:
        return True


def parse_frontmatter(text: str):
    """Return (dict, body, ok). Uses PyYAML when available, else a simple parser."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text, False
    raw, body = m.group(1), m.group(2)
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is not None:
        # Real YAML parsing, so a header the platform would reject is reported as invalid
        # instead of being quietly tolerated. The usual cause is a colon followed by a space
        # inside an unquoted value; quoting the value fixes it.
        try:
            data = yaml.safe_load(raw)
        except Exception:
            return {}, body, False
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}, body, True
        return {}, body, False
    # Fallback when PyYAML is not installed: a simple line parser (cannot catch invalid YAML).
    data, key = {}, None
    for line in raw.splitlines():
        if re.match(r"^[A-Za-z0-9_-]+:", line):
            key, _, val = line.partition(":")
            data[key.strip()] = val.strip().strip("'\"")
        elif key and line.startswith((" ", "\t")):
            data[key] = (str(data[key]) + " " + line.strip()).strip()
    return data, body, True


def format_problems(fm: dict, fm_ok: bool, nested_skill_md: int = 0) -> list:
    """Rules the platform applies when a skill is installed. A skill that breaks one is rejected."""
    probs = []
    name, desc = str(fm.get("name", "") or ""), str(fm.get("description", "") or "")
    if not fm_ok:
        probs.append("frontmatter is missing or not valid YAML (a colon followed by a space inside an unquoted value is the usual cause; quote the value)")
    unexpected = sorted(set(fm) - KNOWN_KEYS)
    if unexpected:
        probs.append(f"unexpected frontmatter keys {unexpected} (allowed: {sorted(KNOWN_KEYS)})")
    if not name:
        probs.append("name is missing")
    elif not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        probs.append(f"name '{name}' must be kebab-case: lowercase letters, digits, single hyphens, none at the ends")
    if len(name) > 64:
        probs.append(f"name is {len(name)} characters (maximum 64)")
    if not desc:
        probs.append("description is missing")
    if "<" in desc or ">" in desc:
        probs.append("description contains angle brackets")
    if len(desc) > 1024:
        probs.append(f"description is {len(desc)} characters (maximum 1024)")
    comp = fm.get("compatibility")
    if isinstance(comp, str) and len(comp) > 500:
        probs.append(f"compatibility is {len(comp)} characters (maximum 500)")
    if nested_skill_md:
        probs.append(f"{nested_skill_md} other SKILL.md file(s) nested inside; the platform rejects more than one per skill")
    return probs


def classify(rel: Path, skill_dir_rel: Path) -> str:
    inner = rel.relative_to(skill_dir_rel) if skill_dir_rel != Path(".") else rel
    first = inner.parts[0] if len(inner.parts) > 1 else ""
    if inner.name == "SKILL.md" and len(inner.parts) == 1:
        return "skill"
    if len(inner.parts) == 1 and inner.name.upper().startswith(("LICENSE", "NOTICE", "COPYING")):
        return "license"  # legal text: shipped with the skill but never needed in context
    return {"scripts": "script", "references": "reference", "assets": "asset"}.get(first, "other")


def build_inventory(root) -> dict:
    root = Path(root).resolve()
    skill_dirs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "SKILL.md" in filenames:
            skill_dirs.append(Path(dirpath))
    skill_dirs.sort()

    skills = []
    for sd in skill_dirs:
        nested = [o for o in skill_dirs if o != sd and sd in o.parents]
        text = (sd / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        fm, body, fm_ok = parse_frontmatter(text)
        name, desc = str(fm.get("name", "")), str(fm.get("description", ""))

        files, symlinks, hidden = [], [], []
        for dirpath, dirnames, filenames in os.walk(sd):
            dp = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (dp / d) not in nested]
            for fn in filenames:
                p = dp / fn
                rel = p.relative_to(sd)
                if p.is_symlink():
                    symlinks.append(str(rel))
                    continue
                binary = is_binary(p)
                size = p.stat().st_size
                tokens = 0
                if not binary:
                    tokens = est_tokens(p.read_text(encoding="utf-8", errors="replace"))
                if any(part.startswith(".") for part in rel.parts):
                    hidden.append(str(rel))
                files.append(
                    {
                        "path": str(rel),
                        "kind": classify(p.relative_to(root), sd.relative_to(root)),
                        "bytes": size,
                        "binary": binary,
                        "est_tokens": tokens,
                        "reachable_from_skill": False,
                    }
                )
        files.sort(key=lambda f: f["path"])

        # A file can only enter context if something Claude reads points to it. Walk outward
        # from SKILL.md: a file is reachable when its path or file name appears (any case) in
        # SKILL.md or in any file already reached. So FORMS.md -> scripts/x.py counts.
        reached, queue = {"SKILL.md"}, ["SKILL.md"]
        while queue:
            cur = queue.pop()
            try:
                blob = (sd / cur).read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            if "\0" in blob[:8000]:
                continue
            for f in files:
                if f["path"] in reached:
                    continue
                if f["path"].lower() in blob or Path(f["path"]).name.lower() in blob:
                    reached.add(f["path"])
                    queue.append(f["path"])
        for f in files:
            f["reachable_from_skill"] = f["path"] in reached

        text_files = [f for f in files if not f["binary"]]
        # Only files reachable from SKILL.md can be pulled into context; license text and
        # unreferenced files cost nothing unless someone opens them on purpose.
        on_demand = [f for f in text_files if f["kind"] in ("reference", "other") and f["reachable_from_skill"]]
        not_loaded = [
            f for f in text_files
            if f["kind"] == "license" or (f["kind"] in ("reference", "other") and not f["reachable_from_skill"])
        ]
        scripts = [f for f in files if f["kind"] == "script"]
        skills.append(
            {
                "dir": str(sd.relative_to(root)) or ".",
                "name": name,
                "description": desc,
                "description_chars": len(desc),
                "frontmatter_valid": fm_ok and bool(name) and bool(desc),
                "format_problems": format_problems(fm, fm_ok, len(nested)),
                "frontmatter_keys": sorted(fm.keys()),
                "unusual_frontmatter_keys": sorted(set(fm.keys()) - KNOWN_KEYS),
                "allowed_tools": fm.get("allowed-tools"),
                "body_lines": len(body.splitlines()),
                "tokens": {
                    "always_loaded_metadata": est_tokens(name + " " + desc),
                    "loaded_on_trigger_body": est_tokens(body),
                    "on_demand_referenced_files": sum(f["est_tokens"] for f in on_demand),
                    "script_files_if_read": sum(f["est_tokens"] for f in scripts),
                    "shipped_but_not_loaded": sum(f["est_tokens"] for f in not_loaded),
                },
                "files": files,
                "orphan_files": [
                    f["path"] for f in files if not f["reachable_from_skill"] and f["kind"] not in ("skill", "license")
                ],
                "hidden_files": hidden,
                "symlinks": symlinks,
                "binary_files": [f["path"] for f in files if f["binary"]],
                "other_skills_nested_inside": [str(o.relative_to(root)) for o in nested],
            }
        )

    # Plugin-style components that run or load automatically deserve extra scrutiny.
    extras = []
    for pattern in (".mcp.json", "hooks", "hooks.json", "commands", "agents", ".claude-plugin", "plugin.json"):
        for hit in root.rglob(pattern):
            if not any(part in SKIP_DIRS for part in hit.parts):
                extras.append(str(hit.relative_to(root)))
    return {
        "root": str(root),
        "skill_count": len(skills),
        "skills": skills,
        "plugin_style_components": sorted(set(extras)),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    inv = build_inventory(sys.argv[1])
    print(json.dumps(inv, indent=2 if "--pretty" in sys.argv else None))
