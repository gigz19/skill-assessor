# Test design and grading

Goal: find out whether the skill changes the outcome for the better, by enough to justify what it costs. Run the same task twice, once without the skill and once with it, and grade both against criteria written before either run.

This step is the most expensive one in the assessment, which is why it comes last, after the claims report and only if the test gate says go (see SKILL.md Step 4). Everything below is about getting a clear signal from as little work as possible.

## 1. Choose the task

**Source: the claims report.** Use its "Test target". Default to one task aimed at the headline claim. Add a second small task only when the report flagged a gap (headline claim partially supported, or scope overreaching) and aim it at exactly that gap. Never run more than two.

**If the user supplied a task, use theirs.** A real task beats a synthetic one. Still write the criteria first.

Task design rules:
- Phrase the prompt the way a real user would, without naming the skill or using its vocabulary, so the trigger and the instructions are what get tested.
- Keep inputs small (a sample project of 100-300 lines, a one-page brief). The goal is a clear signal at low cost. If the task would be large, tell the user the estimated cost before running it.
- Plant known ground truth where you can (an accidental quadratic loop, two problem clauses in a contract, a required list of items) so scoring is objective rather than a matter of taste.
- Pick a task that exercises the skill's own mechanism. A task Claude does equally well without any skill measures nothing.

## 2. Write the criteria and the grader before any run

Write 4-8 pass/fail criteria that a stranger could check, then save them as `criteria.json` for `scripts/grade.py` (the file documents each type). Mix:
- **Automatic checks** for anything checkable from text or JSON: required content present, forbidden content absent, a number within a bound, a count of matches.
- **A side-effects check** (`only_files`) so a skill that writes extra files or touches things outside the task shows up.
- **Manual items** only for real judgment calls. Give each a one-line rubric, and when scoring them, label the two outputs A and B in random order so the score is blind to which condition produced which.
- **Your own checker** when the list cannot express a check (for example "every color is in this palette"). Write it yourself in the work folder; never grade with code taken from the skill under review.

Be honest about what a check measures. A grader that reads the declared content of a page does not tell you how it renders. When appearance is the point, render it and look at it, or say in the scorecard that rendering was not checked.

## 3. Run both conditions

Use the test runner brief (`roles/test-runner.md`) once per condition.

- **With subagents:** start two fresh subagents in the same turn with the same prompt and inputs. Give the skill path only to the `with` run. Record their reported token use.
- **Inline (claude.ai):** run `without` first, working only from the prompt, then reset the working files and run `with`, following the skill exactly. State the limitation in the scorecard: you read the skill before the baseline run, so the baseline is contaminated. Contamination can only make the baseline look better, so a clear gap in the skill's favor is, if anything, understated, while a small gap or a tie is weaker evidence than it looks.

Run the target's scripts only if the security review cleared them and you read them in full. Run them in the working folder with nothing sensitive in scope.

## 4. Grade and compare

```bash
python <skill-dir>/scripts/grade.py <work>/runs/<task>/criteria.json <work>/runs/<task>/without/outputs --json <work>/runs/<task>/without.grade.json
python <skill-dir>/scripts/grade.py <work>/runs/<task>/criteria.json <work>/runs/<task>/with/outputs    --json <work>/runs/<task>/with.grade.json
```

Keep grade files outside the outputs folders, or the side-effects check will flag them. Then fill in a comparison table:

| | Without skill | With skill |
|---|---|---|
| Automatic criteria passed (of N) | | |
| Manual items (blind scores) | | |
| Quality of deliverable (short note) | | |
| Steps taken | | |
| Approx. tokens, including the skill's own load cost | | |
| Side effects | | |

Read the run reports, not just the outputs. If the `with` run spent most of its effort on steps that did not improve the result, that is a finding about the skill's design. Token counts from subagents are real; inline counts are estimates (characters / 4) and must be labeled so.

## 5. Interpret

- **Clear win:** meaningfully more criteria passed, or clearly better, at a proportionate cost.
- **Marginal:** a small gain. Weigh it against the cost and how often the user would use the skill.
- **No difference:** Claude already did this unaided; the skill is redundant for this task.
- **Worse or riskier:** the skill degraded the result, caused side effects, or slowed things down for no gain. Say so plainly.

## 6. State how strong the evidence is

One pair of runs is an anecdote, because results vary run to run. If budget allows, run two or three per condition and report the spread; otherwise label the result "single run". Always say what the task was, so the user can judge whether it resembles their own use, and list what the criteria could not check.
