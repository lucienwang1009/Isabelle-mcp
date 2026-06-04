# Error codes → what to do

Every failing tool call returns `{"ok": false, "error": {"code", "message",
"correlation_id"}}` and usually a `hint`. Read `error.code` and act:

| `error.code` | Meaning | Fix |
|---|---|---|
| `parse_error` | The Isar/term syntax didn't parse. | Re-read the `message` (it points at the offender), fix quoting/syntax, resend ONE command. Inner terms need `"…"`. |
| `tactic_failed` | The tactic ran but didn't close/advance the goal. | `isabelle_state` to see the real goal; try another tactic, `find_theorems` for a lemma, or `sledgehammer`. Don't repeat the same tactic. |
| `timeout` | The step exceeded `timeout_s`. | Raise `timeout_s`, or simplify/decompose the goal. For sledgehammer this is normal — lower it to fail fast while iterating. |
| `repl_not_found` | `repl_id` is unknown (never opened, closed, or reaped after idle TTL). | Open a fresh REPL and replay your steps. |
| `repl_in_proof` | The REPL is already past `qed` / not where you think. | Open a new REPL, or `isabelle_undo` back to the right point. |
| `proof_not_open` | A proof tactic was sent with no open `proof` block. | State the goal first (`lemma …`), then send proof steps. |
| `file_not_found` | Path is missing or outside the sandbox. | Use a path inside the project (or an `ISABELLE_MCP_ALLOWED_DIRS` root). |
| `session_not_started` | The Isabelle session image isn't up yet. | Wait/retry; if it persists the daemon failed to build the heap. |
| `ir_unavailable` | The I/R daemon is unreachable (likely crashed). | Retry — the manager auto-restarts it; then reopen your REPL (state is lost). |
| `ml_disabled` | Raw ML eval is off. | Set `ISABELLE_MCP_ALLOW_ML=1` only if you truly need raw ML. |
| `invalid_argument` | A tool argument is malformed. | Check the argument against the tool schema. |
| `internal_error` | Unexpected server fault. | Report it with the `correlation_id`; retry the call. |

## General recovery discipline

- **Never** resend the identical failing command and hope — change something.
- After `ir_unavailable`/`repl_not_found`, REPL state is gone: reopen and replay.
- Keep one command per `isabelle_step`; a `parse_error` on a pasted multi-line
  block tells you nothing about which line broke.
- Quote the `correlation_id` when escalating a bug — it ties to the structured
  server log line.
