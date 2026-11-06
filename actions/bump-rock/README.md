# bump-rock

Bumps a single rock in a `canonical/*-rocks` repository to a new upstream
version. It diffs the upstream Dockerfile(s), asks an LLM for an updated
`rockcraft.yaml`, runs the rock's own `tox` sanity tests, and opens a PR
whose only change is that `rockcraft.yaml`.

In CI this runs through the
[Bump Rock Version](../../.github/workflows/bump_rock_version.yaml)
workflow. This document covers running it **locally**. The design is in
[spec.md](../../spec.md).

## Prerequisites

- Python 3.12 and the action's dependencies:

  ```bash
  pip install -r requirements-bump_rock.txt     # from the repo root
  ```

- The `gh` CLI, logged in (`gh auth login`). It is used for the Copilot
  token **and** to open the PR (see the next two sections).
- For the sanity tests (optional with `--skip-tox`): `tox`, `rockcraft` and
  LXD, as for building any rock locally.
- A clone of the target rocks repo, on a clean `main`:

  ```bash
  git clone https://github.com/canonical/pipelines-rocks ~/rocks/pipelines-rocks
  ```

All commands below run from `actions/bump-rock/`.

## ⚠️ Copilot token

The default LLM is `copilot/claude-opus-5.5`, called through the GitHub
Copilot chat-completions API. The token **must belong to a GitHub account
with a Copilot seat**. Any other token gets a 401/403 from the API.

The token is resolved in this order:

1. `COPILOT_GITHUB_TOKEN`, if set: a fine-grained PAT with only the
   *Copilot Requests* permission. This is what CI uses.
2. Otherwise, the `gh` CLI login, read as
   `env -u GITHUB_TOKEN -u GH_TOKEN gh auth token`.

`GITHUB_TOKEN` and `GH_TOKEN` are **deliberately ignored**. They usually hold
a token without Copilot access (a CI token, or a PAT for something else),
and `gh` would return them instead of your login. If you are logged into
`gh` with several accounts, make sure the active one has the Copilot seat:

```bash
env -u GITHUB_TOKEN -u GH_TOKEN gh auth status     # which account is active
gh auth switch --user <your-copilot-user>         # if it's the wrong one
```

To check that the token works before spending a full run (expect `200`):

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $(env -u GITHUB_TOKEN -u GH_TOKEN gh auth token)" \
  https://api.githubcopilot.com/models
```

Each LLM call counts against that account's Copilot **premium requests**,
and model thinking (`--reasoning-effort`, default `high`) makes calls more
expensive. A `run` makes at most `max_sanity_attempts × (1 + max_retries)`
calls, which is 9 with the defaults.

To use OpenRouter instead, export `OPENROUTER_API_KEY` and pass
`--llm openrouter/<vendor>/<model>`.

## ⚠️ Git identity, GPG key and GitHub user must match

`open-pr --confirm` commits in your clone of the rocks repo and pushes the
branch as **you**. Canonical rocks repos usually require **signed commits**,
so the identity on the commit, your GPG key and your GitHub account have to
line up. Otherwise the commit shows as *Unverified* and the PR can't be
merged, or `git commit` fails outright.

By default the commit is authored as `kubeflow-bot`
(`git_ops.GitIdentity`). That is right for CI, but **locally you must
override it** with the email on your GPG key:

```bash
export GIT_AUTHOR_NAME="Your Name"
export GIT_AUTHOR_EMAIL="you@canonical.com"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
```

Then check that everything points at the same person:

| What | Check | Must match |
|------|-------|------------|
| GPG key | `gpg --list-secret-keys --keyid-format=long` | its UID email is `GIT_COMMITTER_EMAIL` |
| Signing config | `git -C <rocks-repo> config commit.gpgsign` / `user.signingkey` | `true` / that key's ID |
| GitHub account | the public key is uploaded under *Settings → SSH and GPG keys*, and the email is a **verified** address of the account | the account you push as |
| Push and PR user | `gh auth status`; `git -C <rocks-repo> remote -v` | the same GitHub account |

`gh pr create` honours `GH_TOKEN` / `GITHUB_TOKEN` if they are set. When
running `open-pr`, unset them or make sure they belong to that same account.
Otherwise the PR is opened by a different user than the one who pushed.

## Running it

Paths below assume the clone from the prerequisites; replace `api-server`
and `2.18.0` with your rock and target version.

```bash
cd actions/bump-rock
ROCK=~/rocks/pipelines-rocks/api-server
OUT=/tmp/bump-api-server

# 1. Inspect the rock (no network, no LLM).
python -m src.bump_rock parse "$ROCK"

# 2. Check the old and new upstream Dockerfile URLs resolve.
python -m src.bump_rock validate-urls "$ROCK" --target-version 2.18.0

# 3. Generate only: one LLM pass, no rockcraft pack. Fast prompt iteration.
python -m src.bump_rock run "$ROCK" --target-version 2.18.0 --out "$OUT" --skip-tox

# 4. Full run: generate + tox pack / export-to-docker / sanity, with retries.
python -m src.bump_rock run "$ROCK" --target-version 2.18.0 --out "$OUT"

# 5. Preview the PR (dry run: prints branch, title and body, touches nothing).
python -m src.bump_rock open-pr ~/rocks/pipelines-rocks --out-dir "$OUT"

# 6. Commit, push and open the PR (see the two warnings above first).
python -m src.bump_rock open-pr ~/rocks/pipelines-rocks --out-dir "$OUT" --confirm
```

`run` works on a copy of the rock under `$OUT/work/`, so your clone stays on
a clean `main` for `open-pr`. Useful `run` flags:

- `--llm copilot/<model>`: pick another Copilot model.
- `--reasoning-effort low|medium|high|xhigh|max|none`: thinking effort
  (Copilot only).
- `--max-sanity-attempts N`: outer generate + tox attempts.
- `--max-retries N`: extra LLM attempts when the validators reject the
  output.
- `--allow-sanity-failure`: exit 0 anyway, so `open-pr` publishes a draft
  PR.

## Output directory

| Path | Content |
|------|---------|
| `rockcraft.yaml.new` | the generated file |
| `metadata.json` | input for `open-pr`: versions, URLs, model, change reasons, reviewer notes, sanity result |
| `Dockerfile.old` / `Dockerfile.new` | the fetched upstream files |
| `attempts/attempt-N/` | per outer attempt: candidate YAML and `tox-<env>.log` tails |
| `attempts/attempt-N/inner-K/` | raw LLM response (change list, notes, YAML) and validator errors |
| `work/` | the rock copy that tox ran in |

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `Copilot API error 401` / `403` | The token's account has no Copilot seat, or the wrong `gh` account is active. See *Copilot token*. |
| `No Copilot token: set COPILOT_GITHUB_TOKEN or log in with gh auth login` | `gh` is not logged in and `COPILOT_GITHUB_TOKEN` is unset. |
| `gpg: signing failed: No secret key` | `GIT_COMMITTER_EMAIL` / `user.signingkey` don't match a local GPG key. |
| PR commit shows *Unverified* | The commit email isn't a verified email of the GitHub account that owns the GPG key. |
| `target repo ... is on branch ...` / `has uncommitted changes` | `open-pr` needs the rocks clone on a clean `main`. |
| `no '# Based on <url>', '# Dockerfile: <url>' or '# Source: <url>' comment` | The rock's `rockcraft.yaml` has no upstream Dockerfile header comment. |
