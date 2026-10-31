#!/usr/bin/env python3
"""Package a skill folder into a .skill file (a zip with the skill folder at its top level).

Usage: package_skill.py <skill-folder> [output-dir]

Applies the same format rules the platform applies at install (allowed frontmatter keys,
kebab-case name, description length and characters, exactly one SKILL.md), refuses to package symlinks (they could
point outside the folder), skips junk files, and overwrites an existing package of the
same name. The folder is zipped exactly as it is, so the package is what was reviewed.
"""
import fnmatch
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import format_problems, parse_frontmatter  # noqa: E402

SKIP_DIRS = {"__pycache__", ".git", "node_modules"}
SKIP_GLOBS = ["*.pyc", ".DS_Store"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    folder = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else folder.parent
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        sys.exit(f"PACKAGE FAILED: no SKILL.md in {folder}")
    fm, _, ok = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    nested = [p for p in folder.rglob("SKILL.md") if p != skill_md and not any(x in SKIP_DIRS for x in p.parts)]
    problems = format_problems(fm, ok, len(nested))
    if problems:
        sys.exit("PACKAGE FAILED: the platform would reject this skill:\n  - " + "\n  - ".join(problems))
    if str(fm["name"]) != folder.name:
        print(f"WARNING: frontmatter name '{fm['name']}' differs from folder name '{folder.name}'")

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{folder.name}.skill"
    files = []
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if any(part in SKIP_DIRS for part in rel.parts) or any(fnmatch.fnmatch(p.name, g) for g in SKIP_GLOBS):
            continue
        if p.is_symlink():
            sys.exit(f"PACKAGE FAILED: symlink found ({rel}); remove it first")
        if p.is_file():
            files.append(p)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, Path(folder.name) / p.relative_to(folder))
    print(f"Packaged {len(files)} files -> {target}")


if __name__ == "__main__":
    main()
