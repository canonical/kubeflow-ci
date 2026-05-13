# Spec: AI-assisted Rock Version Bump Workflow

## 1. Summary

A manually-triggered GitHub Actions workflow, hosted in this `kubeflow-ci`
repository, that automates bumping a single rock (in any of the Canonical
Charmed Kubeflow `*-rocks` repositories) to a new upstream version.

The workflow:

1. Takes a target rocks repository, a specific rock (folder) inside it, and a
   target upstream version as inputs from the GitHub UI.
2. Reads the existing `rockcraft.yaml` for that rock and the upstream
   Dockerfile reference encoded as a comment at the top of the file.
3. Diffs the old upstream Dockerfile against the new (target-version) one and
   asks an LLM to produce an updated `rockcraft.yaml` reflecting the changes.
4. Runs the rock's own `tox` sanity tests against the updated rock on the CI
   worker to validate the AI output.
5. Opens a pull request on the target rocks repository with the updated rock
   and waits for the repository's own CI to confirm it stays green.

The outcome of a successful run is a **PR on the target rocks repo whose CI
passes**. The outcome of an unsuccessful run is a failed workflow with logs
that explain at which stage the bump went wrong.

## 2. Goals / Non-Goals

### Goals

- Reduce manual effort of routine version bumps for rocks that mirror a
  single upstream Dockerfile.
- Keep the source of truth on the target rocks repo (PR-based): no auto-merge,
  human always reviews.
- Validate AI output **before** opening a PR using the rock's pre-existing
  `tox -e sanity` (and pack) tests, so reviewers never see PRs that fail the
  obvious checks.
- Be model-agnostic via a thin abstraction; the live backend is OpenRouter
  (OpenAI-compatible chat-completions API), which lets us choose any
  Anthropic / non-Anthropic model behind one key.

### Non-Goals

- Auto-merging PRs.
- Bumping multiple rocks in a single run (one rock per workflow trigger).
- Handling rocks whose `rockcraft.yaml` is not derived from a single upstream
  Dockerfile (those will be detected and the workflow will fail fast with a
  clear message).
- Refactoring or modernizing the rock beyond what the upstream diff requires.
- Owning the rock's CI logic — we re-use the existing `tox.ini` in the rock
  folder.

## 3. Assumptions about Target Rocks Repos

These assumptions hold for repos like
[kserve-rocks](https://github.com/canonical/kserve-rocks) and equivalents
(katib-rocks, kfp-rocks, etc.).

- The repo root contains one folder per rock (e.g. `pmmlserver/`,
  `sklearnserver/`, …).
- Each rock folder contains:
  - `rockcraft.yaml` whose first non-empty comment lines reference the
    upstream Dockerfile(s), in the form:
    ```
    # Based on https://github.com/<org>/<repo>/blob/<ref>/<path>/<name>.Dockerfile
    ```
    where `<ref>` is a git tag/branch/SHA that encodes the current version.
  - `tox.ini` with at least `pack`, `export-to-docker`, and `sanity`
    environments (see [pmmlserver/tox.ini](../kserve-rocks/pmmlserver/tox.ini)).
  - A `tests/` directory used by `tox -e sanity`.
- Each rock folder MAY contain `rock-ci-metadata.yaml` — we do not modify it.
- The target repo has a CI workflow that builds and tests rocks on PRs; that
  workflow is the final gate.

If any of these assumptions don't hold for a given (repo, rock) the workflow
must fail fast with a clear diagnostic, not silently produce a broken PR.

## 4. Workflow Inputs (`workflow_dispatch`)

| Input            | Required | Example                                       | Notes |
|------------------|----------|-----------------------------------------------|-------|
| `rocks_repo`     | yes      | `canonical/kserve-rocks`                      | `owner/repo` form. |
| `rock_name`      | yes      | `pmmlserver`                                  | Folder name in that repo. |
| `target_version` | yes      | `0.18.0`                                      | The new upstream version; what `version:` in `rockcraft.yaml` will become and what replaces `<ref>` in the upstream URL. |
| `model`          | no       | `deepseek/deepseek-v4-pro` (default)          | OpenRouter model id override. |
| `dry_run`        | no       | `false` (default)                             | If `true`, run everything but skip the final PR push. |

PRs are always opened against `main` on the target rocks repo. The branch is
not user-configurable to keep the workflow predictable; if a non-`main` flow
becomes necessary, it's a future-work item.

## 5. High-Level Flow

```
[user clicks Run workflow in GitHub UI]
            │
            ▼
[checkout kubeflow-ci]
            │
            ▼
[clone target rocks_repo @ main into workspace]
            │
            ▼
[locate rock folder + parse upstream Dockerfile URL(s) and old version]
            │
            ▼
[validate URLs; if broken, attempt bounded repair (tree-listing + optional
 LLM-guessed path, re-validated by HTTP fetch). Record repairs for PR body.]
            │
            ▼
[fetch old Dockerfile @ old version, new Dockerfile @ target_version]
            │
            ▼
[build LLM prompt: old rockcraft.yaml + Dockerfile diff + target_version]
            │
            ▼
[call LLM → updated rockcraft.yaml  (only this single file may change)]
            │
            ▼
[write updated rockcraft.yaml into rock folder on a new branch]
            │
            ▼
[run tox -e pack, export-to-docker, sanity inside the rock folder]
            │
            │  on failure → regenerate via LLM, retry — capped at
            │  MAX_SANITY_ATTEMPTS = 3 total. tests/* never modified;
            │  any LLM-suggested test changes recorded for PR body.
            ▼
[push branch to target rocks_repo, open PR with single-file diff]
            │
            ▼
[poll target repo PR checks; report green/red back as job status]
```

## 6. Detailed Stages

### 6.1 Trigger & Setup

- Workflow file lives at
  `.github/workflows/bump_rock_version.yaml` in this repo.
- Runs on `ubuntu-latest` (small GH-hosted runner). LXD/rockcraft needs the
  runner; if `ubuntu-latest` is insufficient, fall back to a larger runner
  label — this is an explicit open question (§9).
- Installs: `rockcraft`, `tox`, `yq`, `gh`, `python` toolchain, `docker`.

### 6.2 Clone Target Repo

- Clone `rocks_repo` at `main` into a working directory using a token
  (`ROCKS_REPO_PAT`, see §7) with permission to push branches and open PRs.
- Configure git user as a bot identity (e.g. `kubeflow-bot`).
- Fail fast if `rock_name` is not a directory in the repo root.

### 6.3 Parse Existing Rock Metadata

From `<rock_name>/rockcraft.yaml`:

- Extract the upstream Dockerfile URL(s) from the leading `# Based on …`
  comments. There MAY be more than one Dockerfile — all must be parsed.
- Parse the `<ref>` segment of each URL (this is the current upstream
  version). If multiple URLs reference *different* refs, fail with a clear
  message — those rocks need manual handling.
- Read the current `version:` field from `rockcraft.yaml`.

### 6.4 Validate & Repair Upstream Dockerfile References

The `# Based on` URL is human-maintained and is sometimes wrong, stale, or
pointing at a moved file (e.g. the upstream renamed the Dockerfile, changed
the directory layout, or the URL was never correct to begin with). Before
fetching, the workflow must validate the URL and, when broken, attempt to
repair it.

Steps per parsed URL:

1. **Validate the old URL** by performing an HTTP `HEAD`/`GET` for the raw
   content at the recorded `<ref>`. If it returns 200, the URL is good.
2. **If the old URL is broken** (404 or non-2xx), try a small bounded
   repair search before failing:
   - Resolve the upstream `<org>/<repo>` and `<ref>` from the URL.
   - Use the GitHub API to list the tree at `<ref>` and look for files whose
     basename matches the recorded Dockerfile name (e.g. `pmml.Dockerfile`).
   - If that yields a unique match, treat it as the candidate corrected URL
     and re-validate (HTTP 200 check). Cap the search to a single tree
     listing of the repo at that ref — no recursive scraping.
   - If still no match, optionally ask the LLM for a best-guess corrected
     path given: original URL, repo's top-level tree at `<ref>`, and rock
     name. The LLM's suggestion MUST be re-validated by HTTP fetch — never
     trust a guessed URL without confirming it actually exists.
3. **If the URL was repaired**, record this and include a note in the PR
   description so the human reviewer knows the comment line was corrected.
   The new `rockcraft.yaml` will contain the repaired URL.
4. **If repair fails**, the workflow exits with a clear diagnostic listing
   the original URL, the attempted candidates, and a suggestion to fix the
   `# Based on` comment manually.

Validation always happens for both the old `<ref>` and the new
`<target_version>` form of each URL.

### 6.5 Fetch Upstream Dockerfiles

- For each (now-validated) upstream URL:
  - Fetch the raw content at the existing `<ref>` (old).
  - Fetch the raw content with `<ref>` replaced by `target_version` (new).
- If the new fetch 404s after the repair attempt in §6.4 also fails for the
  new ref, fail with: "Upstream Dockerfile not found at `<target_version>`
  for `<URL>`".

### 6.6 Generate Updated `rockcraft.yaml` via LLM

Inputs to the prompt:

- Current `rockcraft.yaml` (verbatim).
- For each Dockerfile pair, the **unified diff** between old and new
  (sending full files only when the diff is large enough that context would
  be lost — to be tuned).
- The desired `target_version`.
- A short instruction block describing the conventions (e.g. update the
  `# Based on` URLs to point at the new ref, update `version:`, update
  `source-tag:` in parts, update package versions referenced in
  `override-build` only when the Dockerfile diff shows them changing, do not
  reorganize unrelated sections, preserve comments).

Output contract: the LLM must return **only** the new `rockcraft.yaml`
content. The workflow validates:

- It is valid YAML.
- `name` is unchanged.
- `version` equals `target_version`.
- The `# Based on` URLs now reference `target_version`.
- **Only `rockcraft.yaml` was modified.** Files under `tests/`, `tox.ini`,
  `rock-ci-metadata.yaml`, and anything else in the rock folder MUST remain
  byte-identical to what was checked out from `main`. If the LLM returns a
  patch that touches any other file, that change is discarded and the
  workflow records the LLM's suggestion for the PR body (see §6.8).

If validation fails, retry up to **`MAX_LLM_RETRIES` = 2** times (i.e. 3
total attempts) with the validation error appended to the prompt. After
that, fail.

### 6.7 Run Sanity Tests

Inside the rock folder, on the updated `rockcraft.yaml`:

- `tox -e pack` — must succeed (this builds the rock).
- `tox -e export-to-docker` — must succeed (loads into local docker).
- `tox -e sanity` — must succeed (the per-rock pytest checks in `tests/`).

#### Retry guardrails (must not loop)

- A single sanity-test pass is one "attempt".
- If sanity fails, the workflow MAY feed the failure log back to the LLM and
  regenerate `rockcraft.yaml` — but the **total** number of attempts is
  capped by **`MAX_SANITY_ATTEMPTS` = 3** (1 initial + 2 re-generations).
- The cap applies per workflow run; there is no exponential backoff loop and
  no "until green" mode.
- Each attempt has its own LLM call budget (§6.6 retries), and those are
  independent — so worst case per run is
  `MAX_SANITY_ATTEMPTS × (1 + MAX_LLM_RETRIES) = 9` LLM calls.
- Tests in `tests/` are **never** modified by the workflow during retries
  (see §6.6 single-file constraint). If the model believes a test must be
  updated to accommodate the bump, that suggestion is recorded for the PR
  body and not applied.
- When the cap is hit, the workflow **still opens a PR — as a draft** —
  so a human engineer has the LLM's best-effort `rockcraft.yaml` to
  triage instead of nothing. The PR body prepends a "⚠️ Sanity tests did
  not pass" banner and includes the last `tox -e <env>` log tail per
  attempt in a `## Sanity-test failure` section. `metadata.json` carries
  `sanity_ok=false` for downstream consumers. Opting out of this
  behaviour is a single `--allow-sanity-failure` flag away on the CLI.

### 6.8 Open PR

- Create branch `bump/<rock_name>-<target_version>` on the target repo (if
  it already exists, append a short timestamp suffix).
- The PR diff contains a single file: `<rock_name>/rockcraft.yaml`.
- Commit message: `chore(<rock_name>): bump to <target_version>`.
- PR title: `chore(<rock_name>): bump to <target_version>`.
- PR body (templated): summarises old → new version, links to upstream
  Dockerfiles old/new, lists which sanity tests ran on the CI worker, notes
  that the change was AI-generated and requires human review, and includes a
  **"Reviewer follow-ups"** section that may contain:
  - Any `# Based on` URL that had to be repaired (§6.4) — old URL, new URL,
    and how it was discovered.
  - Any test/tox changes the model suggested but the workflow refused to
    apply (§6.6), reproduced verbatim, so the reviewer can decide whether to
    incorporate them in a follow-up commit on the PR branch.
- Apply a label such as `ai-generated` if it exists on the target repo
  (best-effort, don't fail if the label is absent).

### 6.9 ~~Wait for Target Repo CI~~ (removed)

Initial design called for the workflow to poll the target repo's PR
checks via `gh pr checks --watch` before declaring success. Removed in
v1: keeping the dispatch run fast and decoupled from target-repo CI
duration is more useful, since the target-repo CI status is visible on
the PR itself and on whatever notification surface the maintainer
already uses. If we ever want it back, it's a single `gh pr checks
--watch --fail-fast <url>` step inside the same job's timeout.

## 7. Secrets, Permissions & Timeouts

### 7.1 Secrets

Stored as repository or organization secrets in `kubeflow-ci`:

| Secret              | Purpose |
|---------------------|---------|
| `OPENROUTER_API_KEY`| Required for every run. Used to call OpenRouter's chat-completions API for the LLM generation step (§6.6). |
| `ROCKS_REPO_TOKEN`  | Token used for all GitHub operations against the target rocks repo (clone, push branch, open PR, read PR checks). |

The workflow MUST refuse to run if `OPENROUTER_API_KEY` is missing.

### 7.2 Token permissions (principle of least privilege)

`ROCKS_REPO_TOKEN` should be a fine-grained PAT or a GitHub App installation
token scoped **only** to the rocks repos it needs to operate on (ideally
configured per-repo, not org-wide). The required permissions are the
minimum set that lets the workflow push a branch, open a PR, and read PR
checks:

| Scope         | Access      | Why |
|---------------|-------------|-----|
| Contents      | Read & write | Clone the repo, create a branch, push the single-file change. |
| Pull requests | Read & write | Open the PR, update its title/body, add labels. |
| Metadata      | Read         | Implicitly required by GitHub for any fine-grained PAT. |
| Checks        | Read         | Poll PR check status in §6.9. |
| Actions       | Read         | If the PR triggers Actions workflows we want to observe their status. |

Explicitly **NOT** granted (must remain unchecked):

- Administration, Secrets, Variables, Environments, Webhooks, Workflows
  (write), Packages, Deployments, Pages, Issues (write), Discussions,
  Branch protection rules.

The `GITHUB_TOKEN` provided by Actions for `kubeflow-ci` itself is **not**
used to touch the target rocks repo — it can't, by design, reach other
repos. Its permissions in the workflow file should be set to the minimum
needed for the run itself (`contents: read`).

### 7.3 Timeouts

To make sure a runaway workflow can't sit forever consuming credits or LLM
budget, every level has an explicit timeout:

| Level                          | Default | How it's enforced |
|--------------------------------|---------|-------------------|
| Whole workflow run             | 90 min  | `timeout-minutes` on the job in the workflow YAML. |
| Single LLM call                | 5 min   | HTTP client timeout in the calling script. |
| `tox -e pack`                  | 30 min  | `timeout` wrapper around the tox invocation. |
| `tox -e sanity` (+ export)     | 15 min  | Same. |
| ~~Target-repo CI polling (§6.9)~~ | n/a  | Removed in v1; the workflow returns as soon as the PR is opened. |

These caps are conservative ceilings, not target durations. The whole-job
timeout is the final backstop: even if a sub-step's wrapper misbehaves, the
GitHub runner will terminate the job.

## 8. Files Added in This Repo

- `.github/workflows/bump_rock_version.yaml` — the `workflow_dispatch`
  workflow.
- `actions/bump-rock/` — composite action or scripts that implement the
  stages above. Suggested layout:
  - `actions/bump-rock/action.yaml`
  - `actions/bump-rock/src/` — Python scripts for parsing, LLM calls,
    validation. Python because the rest of this repo's tooling is Python and
    the SDKs are first-class.
- `requirements-bump_rock.in` / `requirements-bump_rock.txt` — pinned deps
  (`anthropic`, `httpx`, `pyyaml`, `gitpython` or `gh` CLI, `pygithub`,
  etc.).

No changes to existing files except possibly `tox.ini` if we want a local
dev `tox -e bump-rock` entry point (optional, decide during implementation).

## 9. Open Questions / Risks

1. **Runner size**: ~~building rocks with rockcraft inside `ubuntu-latest` may
   need LXD, which historically needs nested virt or a larger runner.~~
   **Resolved (v1)**: the workflow installs LXD + rockcraft via the manual
   `sudo snap install lxd && lxd init --auto` + `sudo snap install rockcraft
   --classic` pattern already used by
   `canonical/charmed-kubeflow-workflows/.github/workflows/build-rock.yaml`,
   and re-enters the shell via `sudo --user "$USER" --preserve-env` so the
   lxd group applies. Disk pressure handled by `jlumbroso/free-disk-space`.
   A `skip_sanity` workflow input is the escape hatch for rocks whose
   `tox -e pack` exceeds the GHA runner ceiling.
2. **Multi-Dockerfile rocks** (e.g. `huggingfaceserver` vs
   `huggingfaceserver-cpu`): out of scope for v1 if they share one
   `rockcraft.yaml` with multiple `# Based on` lines pointing to *different*
   files but the *same* ref — supported. Different refs → fail fast.
3. **LLM determinism**: even with temperature 0, output can vary. Validation
   step (§6.5) catches obvious issues but not semantic correctness — the
   sanity-test step (§6.6) is the real gate.
4. **Prompt size**: very large Dockerfile diffs may exceed context limits.
   Default to sending full old + new Dockerfiles plus a diff hint; chunking
   strategy is a v2 concern.
5. **Sanity coverage**: the rock's existing `tests/test_rock.py` checks for
   file presence inside the image, not behavior. A version bump that
   silently breaks runtime behavior may still pass sanity — the target repo's
   own CI is the final safety net, plus human review.
6. **Concurrent runs** on the same `(repo, rock, target_version)` should
   detect an existing branch and either reuse or fail; behavior to be
   decided.
7. **Bot identity**: do we use a Canonical GitHub App or a PAT under a bot
   user? App is preferable long-term; PAT is acceptable for v1.

## 10. Success Criteria for v1

- A maintainer can go to the Actions tab of `kubeflow-ci`, click
  *Run workflow* on **Bump Rock Version**, enter any `canonical/*-rocks`
  repo, any rock folder name in that repo, and a real new upstream
  version, and within the 90-minute job ceiling get a PR opened on that
  target repo against `main`. (The target repo's own CI is responsible
  for verifying the PR is green; the bump workflow does not poll it.)
- The PR diff contains exactly one changed file: the rock's
  `rockcraft.yaml`. Any suggested test changes appear in the PR body, not
  in the diff.
- A failed AI generation, hit retry cap, failed sanity test, or
  unrepairable upstream URL results in a clearly-labelled red workflow run
  and **no PR**.
- The workflow never runs longer than 90 minutes end-to-end thanks to the
  layered timeouts in §7.3.
- The `ROCKS_REPO_TOKEN` carries only the permissions listed in §7.2.
- No secrets are leaked into PR descriptions, commit messages, or logs.

## 11. Out of Scope (Future Work)

- Auto-trigger on upstream releases (Renovate-style).
- Multi-rock batch bumps in one PR.
- Self-healing retry loop where the workflow re-prompts the LLM with the
  CI failure from the target repo and pushes a fixup commit.
- Support for rocks not derived from a single upstream Dockerfile.
