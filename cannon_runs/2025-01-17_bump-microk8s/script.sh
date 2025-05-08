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
  --branch-name kf-6604-bump-microk8s \
  --commit-message "chore(ci): bump microk8s to 1.31

Ref canonical/bundle-kubeflow#1157" \
  --pull-request-title "chore(ci): bump microk8s to 1.31" \
  --pull-request-description "Bump microk8s to 1.31

Ref canonical/bundle-kubeflow#1157" \
  --no-skip-ci \
  bash $SCRIPTPATH/main.sh

