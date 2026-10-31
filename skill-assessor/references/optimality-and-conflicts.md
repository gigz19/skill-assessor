# Conflicts, availability, and optimality

Used by the main agent at the verdict step, after the earlier roles have reported. Environment fit and the permissions footprint are already covered by the security report and the gate, so this file covers three questions: does the skill collide with what is installed, can the user already get it another way, and is it the best option?

## Conflicts with installed skills

1. List the skills available in the current session (the `available_skills` list in your context, plus any the user mentions).
2. Compare descriptions. Two skills conflict when their trigger phrases overlap, so either could fire for the same request, or when they give contradictory instructions for the same task (for example two different house styles for one document type).
3. Report each overlap: which request would trigger both, which would likely win, and whether the new skill duplicates, extends, or replaces the existing one.
4. A broad description ("use for any coding request", "when company design standards apply") can hijack requests that other skills, or the user's own conventions, handle better. Carry the quality reviewer's trigger probes into this judgment.

## Already available another way?

Before recommending an install, check whether the user already has it. Look in the session's skill list, and for well-known skills from a vendor's own repository, check whether the vendor says it is already built in or enabled on the user's plan (a README often says so). If you cannot confirm from the session, tell the user where to look (their skills or settings page) before installing a duplicate. A copy of a skill the user already has adds trigger competition and token cost for nothing.

## Optimality

Ask: for this user and this task, is this skill the best option? Use the evidence already gathered.

1. **No skill.** The baseline run answers this directly. If Claude without the skill got close, the marginal value is small. If the test was not run, say the question is open.
2. **An installed skill or built-in capability.** From the conflict and availability checks: does something already cover the task as well or better?
3. **A leaner version.** Which 20% of the instructions carry most of the value? Name sections that are generic advice Claude already follows, feature lists with no rules behind them, or duplicated content. If a short rewrite would give the same result at a fraction of the tokens, say so and offer to make it (SKILL.md Step 6, "with changes").
4. **Alternatives.** Only when the verdict is borderline or the user asks, run one or two quick web searches for other skills that do the same job and compare them at a glance. Do not install or run anything from search results.
5. **Fit with how often it is used.** A heavy skill for a task done once a year is poor value, because the always-loaded description costs tokens in every conversation. For a niche skill, suggest installing it only when needed.
6. **Fit with whose standards it applies.** A skill that applies a specific organization's rules is the best option only for requests that want those rules, and the wrong one for everything else. Say which requests it suits.

## Outcome

State one of these, with the reason in a sentence:

- **Best available choice:** clear gain over the baseline, proportionate cost, no better alternative found.
- **Good but improvable:** worth using; a leaner or corrected version would be better (say how).
- **Redundant:** Claude, an installed skill, or the user's plan already does this about as well.
- **Better alternative exists:** name it and what makes it better.
