SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"


PR_TITLE="Update GH files for issue templates and Jira automation"
PR_DESC="This PR updates the .github files to
* Ensure we have a file for tasks/enhancements
* Ensure the label bug is always used in bug template
* Ensure there's a jira automation workflow file"
COMMIT_MSG="$PR_TITLE

$PR_DESC"

git-xargs \
    --loglevel DEBUG \
    --repo canonical/bundle-kubeflow \
    --branch-name test \
    --commit-message "$COMMIT_MSG" \
    --no-skip-ci \
    --dry-run \
    --keep-cloned-repositories \
    bash $SCRIPTPATH/repo-modifier.sh
