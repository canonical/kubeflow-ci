# Settings - edit these to your case if you're reusing this file
PULL_REQUEST_TITLE="fix: bump charming-actions to v2.1.1"
BRANCH_NAME="bump-charming-actions-2.1.1"
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
  $NO_SKIP_CI $OTHER_ARGS \
  bash $SCRIPTPATH/main.sh