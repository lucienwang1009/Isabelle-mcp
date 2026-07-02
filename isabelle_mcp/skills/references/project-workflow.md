# ROOT/session project workflow for large proofs

Use this reference when the task touches a local Isabelle project, a custom
`ROOT` session, or a theorem too large to prove as one scratch command.

## Mental model

- A **session** is a built Isabelle heap image plus its imported theories and
  session dependencies. It is not an MCP conversation.
- One I/R daemon runs one session image at a time. It can host many `repl_id`s
  inside that session, but switching sessions relaunches the daemon and
  invalidates old `repl_id`s.
- A session is not rebuilt automatically. If `ROOT` or a dependency theory
  changes, run `isabelle_check_project` before relying on the REPL.
- The `.thy` source plus `isabelle_check_project` is authoritative. REPL success
  is exploration until the proof is written back and the project builds.

## Workflow

1. **Find the project boundary.**
   Locate the target `.thy` and nearest `ROOT`. Read the session name, base
   session, `sessions` dependencies, and listed theories.

2. **Check the project before opening a proof REPL.**
   Use:

   ```text
   isabelle_check_project(root="/path/to/project", session="My_Session")
   ```

   If the target session is found through an extra session directory, pass
   `session_dirs=["/path/to/session-root"]`.

3. **Open the target theory in the built session.**
   Use:

   ```text
   isabelle_open_repl(
     theory="My_Theory",
     session="My_Session",
     session_dirs=["/path/to/project"]
   )
   ```

   Use scratch `theory="Main"` only for isolated experiments unrelated to the
   project imports.

4. **Map the large theorem into named facts.**
   Before trying automation, identify the induction scheme, case split,
   invariants, algebraic cleanup lemmas, and library facts likely needed. Add
   named helper lemmas near the theorem so later steps can cite stable names.

5. **Prove and check one lemma at a time.**
   In the REPL, send one Isar command per `isabelle_step`. When a lemma works,
   write it into the `.thy` file and run `isabelle_check_file` or
   `isabelle_check_project` before building more proof on top of it.

6. **Use automation at the leaves.**
   For each open subgoal, try `isabelle_try0`, targeted `find_theorems`,
   `isabelle_multi_attempt`, then `isabelle_sledgehammer`. If these do not close
   the goal, split it with structured Isar and recurse.

7. **Finish with a strict build.**
   Remove every `sorry`, `oops`, temporary `quick_and_dirty`, and abandoned
   helper theorem. Run `isabelle_check_project`; do not declare the proof done
   from REPL state alone.

## Typical ROOT shapes

Single-project session:

```text
session My_Session = HOL +
  theories
    My_Theory
```

Session depending on another session or AFP entry:

```text
session My_Session = Cook_Levin +
  theories
    My_Theory
```

Or:

```text
session My_Session = HOL +
  sessions
    Cook_Levin
  theories
    "Cook_Levin.Satisfiability"
    My_Theory
```

After editing `ROOT`, rebuild/check before opening the REPL.

## Multi-agent discipline

Multiple agents usually start separate MCP servers and separate I/R daemons.
They do not share REPL state. Coordinate through checked `.thy` files and
`isabelle_check_project`, not through another agent's `repl_id`.

If agents work on different sessions concurrently, each daemon needs its own TCP
port; the MCP server auto-falls back from the default port when it is busy.

## Failure recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| Theory not found | Wrong session or missing `session_dirs` | Check `ROOT`, then reopen with the project session and dirs. |
| Lemma found by AFP search but not by `find_theorems` | AFP result is only a source-index hit | Build/load the session that imports the AFP entry. |
| Old `repl_id` fails after opening another session | Daemon relaunched for a different session | Open a fresh REPL and replay from checked source. |
| Project build fails after REPL success | Proof depended on local REPL state or missing imports | Write all helper lemmas/imports into the `.thy`, then rebuild. |
