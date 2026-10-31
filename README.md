# Skill Assessor

A skill for Claude that checks **other** skills before you install them.

Give it a GitHub link, a `.skill`/`.zip` file, a folder, or pasted `SKILL.md` text. It returns a clear verdict, **ADOPT**, **ADOPT WITH CHANGES**, or **REJECT**, along with the evidence behind it. It never installs anything unless you say yes.

## Why

Installing a skill means its author's text becomes instructions Claude follows with your files, tools, and accounts. Skill Assessor answers four questions with evidence:

1. **Is it safe?** Static security review plus a pattern scanner (prompt injection, hidden text, credential access, data leaving the machine, persistence, obfuscation).
2. **Does it do what it says?** Each claim in the description is matched against the instructions that are supposed to deliver it.
3. **Is it worth the cost?** Token cost per loading stage, trigger quality, and conflicts with skills you already have.
4. **Is it better than nothing?** A with-skill vs. without-skill test, run only when the cheaper checks justify it.

## Install

**Claude Code:** copy the `skill-assessor/` folder into `~/.claude/skills/` (all projects) or `.claude/skills/` (one project).

**claude.ai:** download `skill-assessor.skill` from the [Releases](../../releases) page and upload it under Settings → Capabilities → Skills.

Requires Python 3. Only the standard library is needed.

## Use

Just ask:

- "Is this skill safe? https://github.com/owner/repo/tree/main/some-skill"
- "Quick scan of this .skill file"
- "Should I install this?" (with a file attached)

Example verdict:

```
# Assessment: tidy-notes
Verdict: ADOPT WITH CHANGES - safe and useful, but the description fires on any "summary" request.
Source: github.com/example/tidy-notes   Pinned: 3f2c1a9   Mode: subagents

| Check            | Rating   | Reason                                       |
|------------------|----------|----------------------------------------------|
| Provenance       | Limited  | 40 stars, 8 months old, single maintainer    |
| Security         | Pass     | read all 4 files, no scanner hits of concern |
| Claims           | Supported| layout rules and checklist back the claim    |
| Quality          | Caution  | trigger too broad                            |
| Token cost       | Light    | ~60 always, ~400 on trigger                  |
| With/without test| Clear win| 6/6 vs 3/6 criteria                          |
```

## What it touches (its own footprint)

A security tool should be upfront about what it does itself:

- **Network:** only for GitHub links: `codeload.github.com` (download the pinned archive) and `api.github.com` (stars, age, license). Nothing else.
- **Environment:** reads `GITHUB_TOKEN` if set, sending it only to `api.github.com`, for higher rate limits. Optional.
- **Files:** writes only to its own working folder. `--force` refuses to wipe any folder that isn't a previous assessment.
- **Never:** runs code from the skill under review before it passes security review, edits your agent config, or installs without your confirmation.

If you scan this skill with itself, the only hits are in `scripts/`: the scanner's own pattern list and the GitHub fetcher above. The instruction files scan clean, and a test checks that.

## How it works

```
fetch & pin ─▶ security ─▶ gate ─▶ claims + quality ─▶ test gate ─▶ with/without test ─▶ verdict ─▶ install?
               (cheap)     stop on                     skip if claims
                           critical                    are hollow
```

| Path | Purpose |
|---|---|
| `SKILL.md` | The flow and the rules |
| `roles/` | Briefs for the security, claims, quality, and test-runner roles (run as subagents where available) |
| `references/` | Red-flag guide, claim-checking method, test design, scorecard template |
| `scripts/fetch_skill.py` | Download/unpack and pin to a commit SHA or file hash |
| `scripts/inventory.py` | Files, token estimates, orphans, format problems |
| `scripts/scan.py` | Pattern scan; hits are leads, not verdicts |
| `scripts/grade.py` | Grade test outputs against criteria written before the run |
| `scripts/package_skill.py` | Validate and zip a skill into a `.skill` file |

## Limits

A static review reports "no red flags found". That is not the same as "proven safe". One test run is a sample, not proof. The scorecard always states how strong its evidence is.

## Development

```bash
python -m unittest discover tests
python skill-assessor/scripts/package_skill.py skill-assessor dist
```

## License

[MIT](LICENSE)
