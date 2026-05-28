# M0 Manual Setup

Before running the M0 integration tests, the host must have:

1. **Isabelle 2025-2** installed, with `isabelle` on PATH, OR `ISABELLE_HOME` exported.

   Download: <https://isabelle.in.tum.de/website-Isabelle2025-2/>

   Verify:
   ```bash
   isabelle version
   # Expected: Isabelle2025-2: ...
   ```

2. **HOL session image** prebuilt. This takes 5–15 minutes the first time
   on a typical laptop, and is cached afterwards.

   ```bash
   isabelle build -b HOL
   # Verify it is up to date (returncode 0):
   isabelle build -n -b HOL
   ```

3. **Submodules initialized**:

   ```bash
   git submodule update --init --recursive
   ```

4. **uv environment synced**:

   ```bash
   uv sync
   ```

5. (Optional) `IR_AUTH_TOKEN` environment variable can be set to a fixed
   string for reproducibility. If unset, the M0 client generates a random
   token per run.

If any of the above is not satisfied, the integration tests **skip rather
than fail** so that unit tests still pass on CI without an Isabelle install.
