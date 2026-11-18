# Software design — reference

Depth, rationale, and short before/after examples for the checks in [SKILL.md](./SKILL.md).
Load on demand when a finding needs the detail.

The whole set is one idea under different names: **de-complecting**. The keystone question, asked
of any abstraction: **"What does this solve, and what does it hide?"**

---

## 1. Deep vs shallow modules — interface cost vs hidden value

**Interface** = the cost charged to callers: the name, params, return shape, ordering, error
behaviour, everything the caller must know. **Implementation** = the value delivered: everything
hidden. A **deep** module has a *small* interface over a *large* hidden implementation. A
**shallow** module has an interface about as complex as what it wraps — the caller pays roughly
what they would have paid without it.

**Test.** For a unit, list:
1. what a caller must know to use it, and
2. what it handles for them.

Deep = (2) dwarfs (1).

**Shallow smells:**
- Pass-through wrappers that forward with no added guarantees.
- Getter/setter "beans" that expose the whole implementation as an interface.
- Thin `Manager`, `DAO`, `Service` classes whose methods forward one-to-one to a dict, ORM, or
  builtin — the interface is a *renaming* of what it wraps.

**Removing an abstraction is a valid design move.** Fewer, deeper modules beat many shallow ones.
When the caller could do the same thing just as clearly without the wrapper, delete the wrapper.

### Example — shallow

```python
class UserRepo:
    def get(self, id):
        return db.fetch_one("SELECT * FROM users WHERE id=%s", id)

    def save(self, u):
        return db.execute("INSERT INTO users ...", u)

    def delete(self, id):
        return db.execute("DELETE FROM users WHERE id=%s", id)
```

The interface is the same shape as the DB call. Callers still need to know about `db`, SQL
errors, connection state. No leverage.

### Example — deeper

```python
class UserRepo:
    def find_active_by_email(self, email: str) -> User | None: ...
    def upsert(self, user: User) -> User: ...  # returns the persisted, validated form
    def deactivate(self, id: UserId) -> None: ...  # soft-delete + audit + cascade
```

The interface encodes *policy* the caller no longer has to think about: what "active" means, that
upsert is idempotent, that deactivate cascades.

---

## 2. Leaky abstractions

Every non-trivial abstraction leaks. The question is *which* leaks, and whether they are surfaced
or ambushing.

**Method.** Write the interface's one-sentence **promise**. A **leak** is any input where the
promise quietly fails — it hangs, surprises the caller, or is wrong in a way that only makes sense
if you know the internals.

**The leak is conserved.** Surfacing or "fixing" a leak usually *relocates* it. Choose *which*
leak you can live with, and surface it deliberately.

**Best response: surface the leak in the interface.** Options in order of strength:

1. **Make illegal states unrepresentable** — change the type so the bad input can't be expressed.
2. **Encode the leak in the type** — a richer return type (`Result[T, E]`, sum type) so the caller
   must handle the failure mode.
3. **Raise a named exception** the caller can catch specifically.
4. **Document a precondition or parameter** so the leak is at least visible.

**The signature must not lie.** A return annotation that promises a case that never happens is a
leak — e.g. `-> int | None` when the function always returns an `int` or raises. Delete the `None`.

**Prefer fail-loud-early over a plausibly-wrong value.** Returning `None` that errors on misuse
beats a `-1` sentinel that silently corrupts downstream. A crash near the cause is cheaper than
mysterious data hours later.

---

## 3. Coupling, cohesion, seams

### Coupling — aim low

**Coupling:** "if I change A, must I also change B?" The more yes, the tighter.

### Cohesion — aim high

**Cohesion:** "does this unit have one reason to change?"

**The "and" test:** if the honest one-sentence description needs an *and* — *"parses the file
**and** sends the email"* — cohesion is low. That *and* marks a split.

### Seams — how you get low coupling

A **seam** is a place you can change behaviour without editing there. You make one by depending on
something **passed in** (a parameter, an injected object) rather than **reached out to** (a
global, a hardcoded class, an import-and-call).

Seams are where tests slot fakes and where implementations swap.

### Hard-to-test is a coupling signal

If you can't test A without dragging in B (a real DB, the wall clock, the network), they're welded and there's no seam. **The testing friction is diagnostic** — fix it by adding the seam instead of mocking harder.

### Least coupling is no coupling

Two structures that must agree can often collapse into one so they *can't* drift. Prefer to **derive** instead of storing. If a `total` field must always equal `sum(items.price)`, delete the field and compute it.

### Temporal coupling

Methods that must be called in a certain order or timing for correctness, with the required order
left implicit. Classic case: a query that reads state only another method updates.

Fix by injecting the needed input rather than inferring it from history — take the value as a
parameter instead of relying on a prior `set_context()` call.

---

## 4. Simple vs easy + Beck's four rules

**Simple** = un-braided (one role / concept / dimension). Objective; about the *thing*.
**Easy** = familiar, close at hand, few keystrokes. Relative; about *you*.

We habitually trade *simple* for *easy* and pay in complexity later. **Complecting** = braiding
things together = the enemy.

**The "or" test:** a single thing that means A *or* B — one field carrying two meanings, one
number that is both a value and a not-found flag, one endpoint that behaves two ways depending on
a header — is complected. Separate them.

### Beck's four rules of simple design — in priority order

Higher rule breaks ties with lower:

1. **Passes the tests.**
2. **Reveals intention.**
3. **No duplication.**
4. **Fewest elements.**

Because **2 outranks 3**, **incidental** duplication — code that merely looks alike but changes
for *different* reasons — stays split. Only **real** duplication — one concept expressed twice —
gets merged.

**Same-reason-to-change** is the test. If two blocks look the same today but a plausible future
requirement would change one and not the other, they are incidental. Keep them separate.

---

## 5. Tidy First economics

Complexity is **debt** you pay interest on. Tidying is **investment**. **When** to tidy — before
the change, after it, or never — is a **financial** decision, not a moral one.

**Tidy first** when both hold:
- the tidy makes the imminent change easier, and
- the tidy is small and safe.

**Defer** when the code is unlikely to change soon, or when the tidy is large and risky enough to
need its own review.

**Corollary — "make the change easy, then make the easy change."** If a change feels awkward,
that awkwardness is *information*: a responsibility wants to be extracted first. Extract it, then
the change is trivial.

Prefer many small structural steps over one large one. Each step should leave the code green.

---

## Cross-cutting reminders

- **Design ≠ correctness.** This lens covers structure only. If you notice a logic bug, record it
  in a separate note and keep it out of design findings.
- **Language-agnostic.** Examples above use Python-ish syntax for brevity; the principles apply
  in any language.
- **Neutral heuristics → concrete findings.** State the principle, then the *specific* symptom in the code with a file:line reference. Vague findings ("this feels coupled") are noise.
