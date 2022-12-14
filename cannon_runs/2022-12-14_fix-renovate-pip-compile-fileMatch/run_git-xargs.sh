# Settings - edit these to your case if you're reusing this file
PULL_REQUEST_TITLE="fix: pip-compile fileMatch pattern in renovate.json"
BRANCH_NAME="fix-renovate-pip-compile-fileMatch"
COMMIT_MESSAGE="Fixes the fileMatch pattern used by the Renovate bot for pip-compile files.  See [this argo-operators PR](https://github.com/canonical/argo-operators/pull/71) for a full description of the fix."  # Also used as the PR description
NO_SKIP_CI="--no-skip-ci"  # If the PRs opened should trigger tests, leave this in.  Else, comment this out
# OTHER_ARGS="--loglevel DEBUG --dry-run --draft"  # Useful during testing.  Comment it out during real runs

# Main (you probably don't need to change things below here)

# Get the absolute path to where this script lives, so we can copy files
# from here without knowing that path ahead of runtime.
# Taken from https://stackoverflow.com/a/4774063/5394584
# Seems like there's cases where this might not work, but generally good?
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

# Execute
# during testing, use:
#   --loglevel DEBUG --dry-run --draft\
# NOTE: The script path passed as the positional arg below must be absolute, not relative
git-xargs \
  --repos repos.txt \
  --branch-name "$BRANCH_NAME" \
  --pull-request-title "$PULL_REQUEST_TITLE" \
  --commit-message "$COMMIT_MESSAGE" \
  $NO_SKIP_CI $OTHER_ARGS \
  bash $SCRIPTPATH/main.sh