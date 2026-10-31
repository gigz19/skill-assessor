# Changelog

## 1.0.0

First public release.

- Works in Claude Code on Windows, macOS, and Linux as well as claude.ai: no hardcoded sandbox paths, and `grade.py` no longer crashes on Windows.
- `fetch_skill.py --force` refuses to wipe a folder that isn't a previous assessment.
- Role briefs moved from `agents/` to `roles/` so they aren't mistaken for plugin subagents.
- Instruction files reworded so the skill scans clean against its own scanner.
- Shorter trigger description (808 of 1024 characters).
- Added `license: MIT` to the frontmatter.
- Added tests (`tests/`).
