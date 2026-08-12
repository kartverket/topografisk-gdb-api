# FKB-Bane description — deferred design notes

Issues discovered while translating FKBBane 5.0 from QMS format.
None are blockers for the current PoC; all have a known resolution path.

---

## 1. `sluttdato` — lifecycle semantics unresolved

`sluttdato` marks the end of an object's lifetime ("this version was superseded
or ceased to exist"). The QMS description says the property is set by the
management system (*forvaltningssystemet*), but the NGIS JSON Schema does **not**
mark it `readOnly`.

Current treatment: plain optional `timestamp` field, client-provided.

Open question: the management system that archives ended objects likely needs
a separate write path (e.g. a dedicated "close object" process) rather than
an ordinary PATCH. Whether this becomes `server_managed`, a process endpoint,
or a soft-delete convention is a design decision for the production API.

---

## 2. Norwegian characters in field names — identity loss

`SafeIdentifier` is constrained to `^[a-z_][a-z0-9_]*$`. The converter
transliterates ø→o, æ→ae, å→a and lowercases everything, which means camelCase
word boundaries that contained Norwegian characters are lost:

| Original QMS name      | Generated identifier      |
|------------------------|---------------------------|
| `nøyaktighet`          | `noyaktighet`             |
| `nøyaktighetHøyde`     | `noyaktighethoyde`        |
| `datafangstmetodeHøyde`| `datafangstmetodehoyde`   |
| `høydereferanse`       | `hoydereferanse`          |

The generated YAML is valid and the system works, but lossy if we need to
represent exact data back to a user through the API.
A future PR could extend `SafeIdentifier` to allow
Unicode letters (PostgreSQL supports quoted Unicode identifiers) or to preserve
camelCase before lowercasing (e.g. insert `_` before each uppercase letter that
followed a lowercase one).
