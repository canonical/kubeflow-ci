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
  --branch-name kf-6641-update-python-dependencies-second \
  --commit-message "chore: update python dependencies + pin pip" \
  --pull-request-title "chore: update python dependencies + pin pip" \
  --pull-request-description "* Pin pip to 24.2 due to https://github.com/jazzband/pip-tools/issues/2131
* Update python dependencies using 'tox -e update-requirements'

Ref canonical/bundle-kubeflow#1177" \
  --no-skip-ci \
  bash $SCRIPTPATH/main.sh

