# AGENTS.md

Operational notes for AI agents (and humans) working in this repo.

## What this repo is

CI/automation for Canonical's Charmed Kubeflow team. Holds GitHub Actions,
helper scripts, and scheduled workflows used across the team's charm and
rock repositories. There is no application code here — everything is glue.

## Top-level layout

- `actions/<name>/` — composite or Python-backed GitHub Actions. Each
  action self-contains `action.yaml`/`action.yml`, optional `src/` and
  `tests/`, and its own README.
- `.github/workflows/*.yaml` — repo-level workflows (lint, PR tests,
  scheduled credential syncs, etc.).
- `scripts/` — standalone Python utilities invoked from tox envs.
- `cannon_runs/` — historical batch-release run artifacts; rarely touched.
- `requirements-<name>.in` / `requirements-<name>.txt` — per-tool dep
  pins. `.in` is human-edited, `.txt` is the `pip-compile` output.

## Python environment

Use a standard-library `venv` named `venv/` at the repo root (already in
`.gitignore`). All commands below assume it is activated.

```bash
python3 -m venv venv                  # first time only
. venv/bin/activate
pip install pip-tools tox             # bootstrap
```

## Tox is the entry point for everything

Always run Python tasks through tox so deps stay isolated and the same
commands work locally and in CI.

```bash
tox -e lint                  # codespell + flake8 + isort + black
tox -e fmt                   # autofix isort + black
tox -e update-requirements   # regenerate all *.txt lockfiles
tox -e test_branch_creation  # tests for scripts/branch_creation.py
tox -e test_bump_rock        # tests for actions/bump-rock/
```

Adding a new tox env: copy the shape of an existing `test_*` env in
[tox.ini](tox.ini). Use `changedir` when the tests need a specific cwd
(see `test_bump_rock` for the pattern).

## Convention for Python-backed actions

Mirror [actions/get-charm-paths/](actions/get-charm-paths/) or
[actions/bump-rock/](actions/bump-rock/):

- `actions/<name>/action.yaml` — composite action wiring.
- `actions/<name>/src/` — Python module(s). `src/__init__.py` makes it a
  package; internal imports use `from .other import X`.
- `actions/<name>/tests/` — pytest tests. Import the code under test as
  `from src.module import X`, and **run pytest from the action dir** so
  `src.` resolves. A tox env handles `changedir` for you.
- Runtime deps in `actions/<name>/requirements.in/.txt`, test deps in
  `actions/<name>/requirements-test.in/.txt` (usually `-r requirements.in`
  + `pytest` + whatever mocking lib). Older tools still keep top-level
  `requirements-<name>.in/.txt` files.

## Conventions for code

- Every `.py` starts with `# Copyright <YYYY> Canonical Ltd.` and a
  `# See LICENSE file for licensing details.` line. `flake8` enforces it.
- Line length 99, Black formatted, isort with Black profile. Google
  docstring style.
- Prefer typed dataclasses for structured data over raw dicts.
- Tests use `pytest` with `responses` for HTTP mocking and stdlib
  `unittest.mock.patch` for subprocess.

## The bump-rock action specifically

See [actions/bump-rock/README.md](actions/bump-rock/README.md) for running
it locally (Copilot token, GPG/identity setup, retry loops). Quick map:

- [src/rockcraft.py](actions/bump-rock/src/rockcraft.py) — parse a rock's
  `rockcraft.yaml` (extract `# Based on` URLs + `version`).
- [src/urls.py](actions/bump-rock/src/urls.py) — GitHub blob/raw URL model.
- [src/repair.py](actions/bump-rock/src/repair.py) — validate URLs, bounded
  repair on 404 via one GitHub tree listing.
- [src/fetch.py](actions/bump-rock/src/fetch.py) — download old/new
  Dockerfile pair; `retrying_session()` retries connection errors, 429
  and 5xx.
- [src/llm.py](actions/bump-rock/src/llm.py) — Copilot + OpenRouter
  chat-completions clients and a MockClient for tests, picked by
  `--llm provider/model` (default `copilot/claude-opus-5.5`). Copilot calls
  stream with thinking on (`--reasoning-effort`, default `high`).
- [src/generate.py](actions/bump-rock/src/generate.py) — prompt building,
  response parsing (`<change>` / `<reviewer_note>` / `<rockcraft_yaml>`),
  automatic checks incl. "every changed line is listed", and the LLM
  attempt loop.
- [src/system_prompt.md](actions/bump-rock/src/system_prompt.md) — the LLM
  system prompt, loaded verbatim by `generate.py`.
- [src/tox_runner.py](actions/bump-rock/src/tox_runner.py) — `tox -e <env>`
  subprocess wrapper with per-env timeouts and log-tail capture.
- [src/run.py](actions/bump-rock/src/run.py) — sanity attempt loop
  (generate → tox → retry-with-feedback, capped at `MAX_SANITY_ATTEMPTS`).
- [src/bump_rock.py](actions/bump-rock/src/bump_rock.py) — argparse CLI
  with sub-commands `parse`, `validate-urls`, `fetch`, `generate`, `run`.

### Smoke-test commands

```bash
cd actions/bump-rock

# parse / validate / fetch don't need a key.
python -m src.bump_rock parse ~/path/to/rocks-repo/<rock>
python -m src.bump_rock validate-urls <rock-dir> --target-version vX.Y.Z
python -m src.bump_rock fetch <rock-dir> --target-version vX.Y.Z --out /tmp/x

# generate / run default to --llm copilot/claude-opus-5.5. The token comes
# from COPILOT_GITHUB_TOKEN, else `gh auth token` (GITHUB_TOKEN / GH_TOKEN
# are ignored since they usually lack Copilot access).
python -m src.bump_rock run <rock-dir> --target-version vX.Y.Z \
    --out /tmp/bump-rock-run --skip-tox      # fast path; no rockcraft pack

# OpenRouter instead needs OPENROUTER_API_KEY.
export OPENROUTER_API_KEY=sk-or-...
python -m src.bump_rock run <rock-dir> --target-version vX.Y.Z \
    --out /tmp/bump-rock-run --skip-tox --llm openrouter/deepseek/deepseek-v4-pro
```

`--skip-tox` exists for prompt iteration. Drop it once you have an
LLM response you trust and want to actually pack the rock.

## The workflow itself

[.github/workflows/bump_rock_version.yaml](.github/workflows/bump_rock_version.yaml)
exposes the pipeline as a `workflow_dispatch` action with inputs:

- `rocks_repo` (e.g. `canonical/kserve-rocks`)
- `rock_name` (e.g. `pmmlserver`)
- `target_version` (e.g. `v0.18.0`)
- `llm` (defaults to `copilot/claude-opus-5.5`; `openrouter/<vendor>/<model>`
  also works)
- `dry_run` (boolean — prints the PR body preview without pushing)
- `skip_sanity` (boolean — bypass `rockcraft pack` + sanity on the runner)
- `max_sanity_attempts` (default `3` — sanity attempts: generate + tox)
- `max_llm_retries` (default `2` — extra LLM attempts within a sanity
  attempt when the automatic checks reject the answer; total = `1 + this`)

It needs these secrets configured on the repo:

- `COPILOT_GITHUB_TOKEN` — fine-grained PAT of a Copilot-seat user with
  only the *Copilot Requests* permission; used by `copilot/*` LLMs.
- `OPENROUTER_API_KEY` — only needed for `openrouter/*` LLMs.
- `ROCKS_REPO_TOKEN` — fine-grained PAT with `contents:write` +
  `pull_requests:write` on the target rocks repo(s), nothing else.

The workflow's own `GITHUB_TOKEN` is locked to `contents: read`. Sanity
tests **do** run on the GHA runner: the workflow installs
LXD + rockcraft and invokes the CLI via `sudo --user "$USER"
--preserve-env` so the lxd group applies. Use the `skip_sanity` input as
an escape hatch if a particular rock's `tox -e pack` exceeds the runner
ceiling.

## Safety rails baked in

- The `run` sub-command always operates on a **copy** of the rock folder
  under `<out>/work/`. The user's checked-out source tree is never
  touched.
- `assert_only_rockcraft_changed()`: after the loop, any
  file other than `rockcraft.yaml` diverging from source aborts the run.
- `open-pr` is dry-run by default. `--confirm` is required to push the
  branch or open the PR; the workflow YAML supplies it only on
  non-`dry_run` runs.
