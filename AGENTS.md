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

Use **pyenv** with the virtualenv named `kubeflow-ci` (already pinned via
`.python-version`, ignored by git). All commands below assume `pyenv exec`
in front, which resolves to that venv.

```bash
pyenv virtualenv 3.12.12 kubeflow-ci      # first time only
pyenv local kubeflow-ci                   # already done; recreates on checkout
pyenv exec pip install pip-tools tox      # bootstrap
```

## Tox is the entry point for everything

Always run Python tasks through tox so deps stay isolated and the same
commands work locally and in CI.

```bash
pyenv exec tox -e lint                  # codespell + flake8 + isort + black
pyenv exec tox -e fmt                   # autofix isort + black
pyenv exec tox -e update-requirements   # regenerate all *.txt lockfiles
pyenv exec tox -e test_branch_creation  # tests for scripts/branch_creation.py
pyenv exec tox -e test_bump_rock        # tests for actions/bump-rock/
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
- Top-level `requirements-<name>.in/.txt` for runtime deps,
  `requirements-test_<name>.in/.txt` for test deps (usually `-r
  requirements-<name>.in` + `pytest` + whatever mocking lib).

## Conventions for code

- Every `.py` starts with `# Copyright <YYYY> Canonical Ltd.` and a
  `# See LICENSE file for licensing details.` line. `flake8` enforces it.
- Line length 99, Black formatted, isort with Black profile. Google
  docstring style.
- Prefer typed dataclasses for structured data over raw dicts.
- Tests use `pytest` with `responses` for HTTP mocking and stdlib
  `unittest.mock.patch` for subprocess.

## The bump-rock action specifically

See [spec.md](spec.md) for the full design. Quick map:

- [src/rockcraft.py](actions/bump-rock/src/rockcraft.py) — parse a rock's
  `rockcraft.yaml` (extract `# Based on` URLs + `version`).
- [src/urls.py](actions/bump-rock/src/urls.py) — GitHub blob/raw URL model.
- [src/repair.py](actions/bump-rock/src/repair.py) — validate URLs, bounded
  repair on 404 via one GitHub tree listing.
- [src/fetch.py](actions/bump-rock/src/fetch.py) — download old/new
  Dockerfile pair.
- [src/llm.py](actions/bump-rock/src/llm.py) — OpenRouter client + a
  MockClient for tests. Default model is `meta-llama/llama-4-maverick`.
- [src/generate.py](actions/bump-rock/src/generate.py) — prompt building,
  post-LLM validators, inner retry loop (spec §6.6).
- [src/tox_runner.py](actions/bump-rock/src/tox_runner.py) — `tox -e <env>`
  subprocess wrapper with per-env timeouts and log-tail capture.
- [src/run.py](actions/bump-rock/src/run.py) — outer sanity loop
  (generate → tox → retry-with-feedback, capped at `MAX_SANITY_ATTEMPTS`).
- [src/bump_rock.py](actions/bump-rock/src/bump_rock.py) — argparse CLI
  with sub-commands `parse`, `validate-urls`, `fetch`, `generate`, `run`.

### Smoke-test commands

```bash
cd actions/bump-rock

# parse / validate / fetch don't need a key.
pyenv exec python -m src.bump_rock parse ~/path/to/rocks-repo/<rock>
pyenv exec python -m src.bump_rock validate-urls <rock-dir> --target-version vX.Y.Z
pyenv exec python -m src.bump_rock fetch <rock-dir> --target-version vX.Y.Z --out /tmp/x

# generate / run need OPENROUTER_API_KEY.
export OPENROUTER_API_KEY=sk-or-...
pyenv exec python -m src.bump_rock run <rock-dir> --target-version vX.Y.Z \
    --out /tmp/bump-rock-run --skip-tox      # fast path; no rockcraft pack
```

`--skip-tox` exists for prompt iteration. Drop it once you have an
OpenRouter response you trust and want to actually pack the rock.

## The workflow itself

[.github/workflows/bump_rock_version.yaml](.github/workflows/bump_rock_version.yaml)
exposes the pipeline as a `workflow_dispatch` action with inputs:

- `rocks_repo` (e.g. `canonical/kserve-rocks`)
- `rock_name` (e.g. `pmmlserver`)
- `target_version` (e.g. `v0.18.0`)
- `model` (defaults to `meta-llama/llama-4-maverick`)
- `dry_run` (boolean — prints the PR body preview without pushing)

It needs two secrets configured on the repo:

- `OPENROUTER_API_KEY` — for the LLM call.
- `ROCKS_REPO_TOKEN` — fine-grained PAT with `contents:write` +
  `pull_requests:write` on the target rocks repo(s). See spec §7.2 for the
  full least-privilege table.

The workflow's own `GITHUB_TOKEN` is locked to `contents: read` (spec
§7.2). Sanity tests **do** run on the GHA runner: the workflow installs
LXD + rockcraft and invokes the CLI via `sudo --user "$USER"
--preserve-env` so the lxd group applies. Use the `skip_sanity` input as
an escape hatch if a particular rock's `tox -e pack` exceeds the runner
ceiling.

## Safety rails baked in

- The `run` sub-command always operates on a **copy** of the rock folder
  under `<out>/work/`. The user's checked-out source tree is never
  touched.
- `assert_only_rockcraft_changed()` defends spec §6.6: after the loop, any
  file other than `rockcraft.yaml` diverging from source aborts the run.
- `open-pr` is dry-run by default. `--confirm` is required to push the
  branch or open the PR; the workflow YAML supplies it only on
  non-`dry_run` runs.
