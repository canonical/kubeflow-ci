SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

BRANCH=kf-4961-kimwnasptd-tasks-jira-automation
PR_TITLE="Update GH files for issue templates and Jira automation"
PR_DESC="This PR updates the .github files to
* Ensure we have a file for tasks/enhancements
* Ensure the label bug is always used in bug template
* Ensure there's a jira automation workflow file"
COMMIT_MSG="$PR_TITLE

$PR_DESC"


git-xargs \
    --loglevel DEBUG \
    --repos repos.txt \
    --branch-name $BRANCH \
    --commit-message "$PR_DESC" \
    --pull-request-title "$PR_TITLE" \
    --pull-request-description "$PR_DESC" \
    --commit-message "$COMMIT_MSG" \
    --no-skip-ci \
    --keep-cloned-repositories \
    bash $SCRIPTPATH/repo-modifier.sh
