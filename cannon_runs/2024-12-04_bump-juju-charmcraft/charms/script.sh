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
  --loglevel DEBUG\
  --repos repos.txt \
  --branch-name kf-6640-bump-juju-charmcraft \
  --commit-message "ci: bump juju to 3.6 + charmcraft to 3.x/stable" \
  --pull-request-title "ci: bump juju to 3.6 + charmcraft to 3.x/stable" \
  --pull-request-description "* Bump juju to 3.6/stable
* For uniformity, use charmcraft from 3.x/stable

Ref canonical/bundle-kubeflow#1176" \
  --no-skip-ci \
  bash $SCRIPTPATH/main.sh

