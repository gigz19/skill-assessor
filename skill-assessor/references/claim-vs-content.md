# Claim vs. content check

Goal: decide, from reading alone, whether the skill's instructions could plausibly deliver what the skill says it does. This is deliberately separate from the live test. A skill can be well written and still not do what its name promises, and catching that by reading is cheap. It also decides whether the test is worth paying for.

## Method

**1. Extract the claims.** Collect every promise from the `name`, the `description`, any README, the introduction of SKILL.md, and headings that advertise capabilities (a "Features" list counts). Phrase each as a testable sentence: "This skill reduces the runtime of a code base." Split compound promises ("faster, cleaner, and more secure code") into separate claims.

**2. Find the mechanism for each claim.** Search the body, scripts, and references for what actually makes the claim true. Good mechanisms are specific and checkable:
- a concrete procedure (steps in an order that leads to the outcome)
- measurable criteria (what counts as "optimized", "secure", "on-brand")
- a verification step (measure before and after, run tests, compare)
- a script or template that does the work deterministically
- domain knowledge the model likely lacks (specific rules, thresholds, values, formats, house conventions)

**3. Rate each claim.**

| Rating | Meaning |
|---|---|
| Supported | Concrete mechanism covers the whole claim, including a way to tell whether it worked, or the skill supplies specific knowledge that is the claim. |
| Partially supported | Mechanism covers only part of the claim, or does the work but has no way to verify it. |
| Unsupported | The claim appears in the description or marketing text; the instructions contain nothing that delivers it. |
| Contradicted or overreaching | The instructions do something different from, or broader than, the claim (for example a skill advertised as read-only analysis that also edits files, or a claim of "any file type" backed by guidance for one). |

**4. Flag vague claims.** Words like *optimize, improve, enhance, best practices, production-ready, secure, clean, fast, smart, comprehensive* mean nothing without a definition. If a skill says "optimizes the code base" and never says optimize for what (runtime, memory, bundle size, readability) or how to measure it, rate the claim no higher than Partially supported and say why. A claim that cannot be verified is a finding in itself.

**5. Check for hollow content.** Instructions that only restate what Claude does by default ("write clean code, follow best practices, handle errors") add cost but no capability. A feature list that describes the behavior of software, with no rule and no script behind it ("smart color selection based on background"), is a claim without a mechanism. Note these, because they feed the token-cost and optimality judgments.

**6. Check scope honesty.** List what the skill touches that the description never mentions. Undisclosed scope is both a claim problem and a security signal.

**7. Pick the headline claim and the test target.** The headline claim is the promise that most explains why someone would install the skill. If it is Supported, the test should confirm it works in practice. If it is only Partially supported, or the scope claim overreaches ("any sort of artifact" backed by guidance for one kind), aim the test at that gap, because that is where the real uncertainty is.

## Worked example (illustrative)

Suppose a skill called *Ponytail* says: "Optimizes the code base."

- Claim extracted: "Given a code base, the skill makes it better optimized."
- Finding A: the body has a procedure that profiles hot paths, ranks bottlenecks, applies changes one at a time, re-measures, and reverts changes that do not help or that break tests. Rating: **Supported**.
- Finding B: the body only tells Claude to rename variables, remove unused imports, and reformat. Rating: **Partially supported**, because it covers tidiness, not optimization.
- Finding C: the body says "analyze the code and make it faster and cleaner" with no steps and no measurement. Rating: **Unsupported** (vague claim, no mechanism); Claude can already do this unaided. If most claims look like this, answer "Worth a live test: NO".
- Finding D: the body also deletes files it judges unused and rewrites configuration. Rating for scope: **Overreaching**, since "optimize" did not promise deletion or config changes.

## Output

The exact report format is in `roles/claims-reviewer.md`. The one-sentence summary should say how much of the headline promise the content supports ("supports about half of it: covers X, does not cover Y"). If most claims are Unsupported or Contradicted, say plainly that the live test is probably not worth running and that this weighs heavily toward REJECT.
