---
name: software-design
description: 'Software-design lens for coding agents. Use when: reviewing a diff or PR, writing a new module / class / API, refactoring existing code, or when explicitly invoked. Applies language-agnostic design heuristics — deep vs shallow modules, leaky abstractions, coupling / cohesion / seams, simple-vs-easy, Beck''s four rules of simple design, Tidy First economics — and produces concrete design findings. Judges *design*, not correctness bugs. Requires interviewing the human to align on intent before writing and to verify shared understanding before critiquing. Trigger keywords: design review, PR review, refactor, new module, new API, new class, code smell, coupling, cohesion, abstraction, tidy first.'
argument-hint: '[review|write|refactor] <target>'
---

# Software design lens

A design lens for four situations: **review**, **write**, **refactor**, **on request**. Judges
*structure* — interfaces, coupling, cohesion, seams, simplicity. Not correctness bugs.

**Keystone question, asked of every abstraction:** *"What does this solve, and what does it hide?"*

One idea under different names: **de-complecting**.

## Plain language — applies throughout

This rule governs how the agent speaks and how it designs. Aim for plain understanding. More is
not better.

**When speaking / writing findings / presenting plans:**

- Say it once, in the shortest form that stays accurate.
- Prefer common words over jargon. If a term of art is needed, define it in one clause.
- **State what the thing *is* and how it *works*. Avoid negations by default.** Negation earns
  its keep only when contrast is doing real work — a change description (before → after), a
  correction of a strong default expectation, or a deliberate contrast against the naive
  alternative. If the reader doesn't need the contrast, drop it.
  - Doc / steady state: *"the repo returns the persisted user."*
  - Commit / change note: *"the repo now returns the persisted user; callers no longer reconcile IDs."*
- Cut filler: *\"it's worth noting that\"*, *\"essentially\"*, *\"basically\"*, *\"in order to\"*,
  hedges (*\"perhaps we might consider possibly...\"*), and restatements of what was just said.
- No throat-clearing intros (*\"Great question!\"*, *\"Let me start by...\"*) and no summary outros
  that repeat the body.
- One idea per sentence. If a sentence needs a semicolon and two commas to survive, split it.
- If a bullet list has one item, it's a sentence. If it has ten, it's an outline.
- Cite `file:line` instead of describing where something is in prose.

**When designing / naming / shaping code:**

- A design a colleague can't explain back in plain English is too clever. Simplify until they can.
- Names should say what the thing *is* or *does*, in the reader's vocabulary — not the framework's,
  not the pattern catalogue's. `SendInvoice` beats `InvoiceDispatchStrategyImpl`.
- One concept per unit. If the name needs an *and*, split it (see the "and" test).
- Prefer boring, obvious solutions over novel ones. Novelty is a cost the reader pays.
- Comments explain *why*. Express the *what* in the code first — clearer names, extracted functions, better types. Reach for a *what*-comment only when the code genuinely can't be made
  clearer (dense algorithm, spec-driven parsing, hot path, section marker).
- Fewer layers, fewer indirections, fewer configuration knobs — until removing one would break a
  real requirement, not a hypothetical one.

## Mandatory interview protocol

This skill requires interviewing the human — to avoid solving the wrong problem or critiquing
code the agent has misunderstood.

**Escape hatch:** honour explicit opt-out only. Phrases like *"just do it"*, *"skip the questions"*,
*"no interview"*, *"go ahead"*, or *"I've already told you enough"* → skip the interview and proceed.
Absent such a phrase, run the protocol every time.

**Question format:** the agent decides per situation. Use the structured question tool for
concrete options or multi-select; use plain chat for open-ended or single follow-ups. Batch
related questions; don't drip them one at a time. Keep each question to one sentence.

### Before writing new code — deep intent interview

Complete the intent interview before proposing any interface or writing any code. Cover:

1. **The actual end goal** — the user's underlying problem, not just the feature they asked for.
2. **Constraints** — performance, deployment, team conventions, existing seams the change must fit.
3. **Prior attempts** — what has been tried or considered and rejected, and why.
4. **Success criteria** — how we will know the change is done and working.
5. **Non-goals** — what we are deliberately *not* solving in this change.

Then produce a **plan** (interfaces, seams, responsibilities, what stays out) and run the **plan
gate** (below). No code before the gate passes.

### Plan gate — hard stop before writing

After presenting the plan, interview the human to confirm:

- They **understand** the plan (ask them to reflect back the key moves, or agree to each in turn).
- They **agree** with it — including any trade-offs you flagged.
- Your assumptions match theirs.

**Write implementation code only after the human explicitly approves.** If the human corrects anything, revise the plan and re-run the gate.

### Before reviewing — shared-understanding interview

Before reporting findings on existing code, verify you and the human have the *same* mental model.
Use **all** of these techniques, adapted to the size of the change:

1. **Restate the code in your own words** and ask the human to confirm or correct.
2. **Ask the human to explain the purpose** of the specific units you intend to critique — hear
   the purpose from them before critiquing.
3. **Surface the invariants and assumptions** you think are load-bearing, and ask whether they hold.
4. **Write each unit's one-sentence promise** (see checks below) and ask the human to confirm it
   matches what the code is *supposed* to guarantee.

Only after this alignment do you report findings.

### Before refactoring — same as writing

Refactoring follows the writing flow: intent interview → plan → plan gate → code. **Plus** the
**Tidy First economics check**: is this tidy worth doing *now* (does it make an imminent change
easier), and is it small and safe? If neither, defer.

## The checks (run these)

Apply on every review, and against your own plan before writing.

- **Deep vs shallow** — for each unit, list (1) what a caller must know and (2) what it handles for
  them. Deep = (2) dwarfs (1). Shallow smells: pass-through wrappers, thin `Manager`/`DAO`/`Service`
  whose methods forward 1:1 to a dict / ORM / builtin. **Removing an abstraction is a valid move.**
- **The promise sentence + leak scan** — write the interface's one-sentence promise. A **leak** is
  any input where the promise quietly fails (hangs, surprises, is wrong in a way that only makes
  sense if you know the internals). Surface the leak in the interface, or make illegal states
  unrepresentable. **Signatures must not lie.**
- **The "and" test (cohesion)** — if the honest one-sentence description contains an *and*
  ("parses the file *and* sends the email"), that *and* is a split.
- **Seam check** — does the unit depend on things **passed in** (parameter, injected object) or
  **reached out to** (global, hardcoded class, import-and-call)? Reach-out = no seam.
- **Hard-to-test = coupling** — if A can't be tested without dragging in B (real DB, wall clock,
  network), they're welded. Testing friction is diagnostic.
- **The "or" test (complecting)** — a single thing that means A *or* B (one field carrying two
  meanings, one number that is both a value and a not-found flag) is complected — separate them.
- **Temporal coupling** — methods that must be called in a certain order for correctness with
  nothing in the interface saying so. Fix by injecting the needed input.
- **Beck's four rules of simple design, in priority order** (higher breaks ties):
  1. **passes the tests** · 2. **reveals intention** · 3. **no duplication** · 4. **fewest elements**.
  Because 2 outranks 3, **incidental** duplication (looks alike, changes for *different* reasons)
  stays split; only **real** duplication (one concept expressed twice) gets merged.

For depth, examples, and rationale, read [reference.md](./reference.md).

## Finding format (for review / on request)

Report findings **most-significant first**. Each finding:

- **(a)** the principle + the check that caught it,
- **(b)** the concrete symptom (`file:line`),
- **(c)** why it bites — a specific failure or maintenance scenario,
- **(d)** the fix. Usually one of: *surface* the leak, *extract* a seam or responsibility,
  *collapse* redundant state, *inject* a dependency, *remove* a shallow wrapper, *split* incidental
  duplication.

Report design findings only. Correctness bugs are out of scope. Correctness bugs can be added if human explicitly says so.

## When writing new code — pre-finalize checks

Before declaring the code done, for every new unit:

- Write its one-sentence promise. A hidden *and* = low cohesion. An *or* = complecting.
- Confirm the interface is **deep** (small surface, large hidden implementation).
- Confirm dependencies are **passed in**, not reached out to.
- Confirm the signature does not lie (no return types promising cases that never happen).

## When refactoring

**Tidy First economics.** Complexity is debt with interest; tidying is investment; *when* to tidy
is a **financial** decision, not moral. Tidy first when it makes the imminent change easier and
the tidy is small and safe. Otherwise defer. Corollary: **"make the change easy, then make the
easy change."** Awkwardness is information — a responsibility wants to be extracted first.
