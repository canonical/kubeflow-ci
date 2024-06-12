#!/usr/bin/env bash
set -x

# NOTE: This did not work.  The patch commands work outside this script,
# but did not work when this script is called by git-xargs.  Couldn't 
# figure out why, so went with a python version instead

# This script:
# * adds a publish.yaml that is manually clickable and works for single and multi-charm repos
# * adds a get-charm-paths.sh needed for the above publish.yaml
# * simplifies the job names
# * preserves whitespace in the yamls, wherever yq is used

# Get the absolute path to where this script lives, so we can copy files
# from here without knowing that path ahead of runtime.
# Taken from https://stackoverflow.com/a/4774063/5394584
# Seems like there's cases where this might not work, but generally good?
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
echo "Copying source files from '$SCRIPTPATH'"

createOrReplaceFile () {
	SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
	SOURCE="$SCRIPTPATH/$1"
	TARGET="$2"
	echo "Copying $SOURCE to $TARGET"
	cp $SOURCE $TARGET
}

echo "I am executing this script from $(pwd)"

# Add the git-charm-paths.sh file
createOrReplaceFile get-charm-paths.sh ./.github/workflows/get-charm-paths.sh

# Overwrite the publish.yaml
createOrReplaceFile publish.yaml ./.github/workflows/publish.yaml

# For each of on_push and on_pull_request, do:
# Rename .jobs.publish-charm.secrets.charmcraft-credentials to .jobs.publish-charm.secrets.CHARMCRAFT_CREDENTIALS
patch .github/workflows/on_push.yaml <<< $(\diff --color -U0 -w -b --ignore-blank-lines .github/workflows/on_push.yaml <(yq eval ".jobs.publish-charm.secrets.CHARMCRAFT_CREDENTIALS = .jobs.publish-charm.secrets.charmcraft-credentials | del(.jobs.publish-charm.secrets.charmcraft-credentials)" .github/workflows/on_push.yaml))
patch .github/workflows/on_pull_request.yaml <<< $(\diff --color -U0 -w -b --ignore-blank-lines .github/workflows/on_pull_request.yaml <(yq eval ".jobs.publish-charm.secrets.CHARMCRAFT_CREDENTIALS = .jobs.publish-charm.secrets.charmcraft-credentials | del(.jobs.publish-charm.secrets.charmcraft-credentials)" .github/workflows/on_pull_request.yaml))

# Simplify workflow names
patch .github/workflows/on_push.yaml <<< $(\diff --color -U0 -w -b --ignore-blank-lines .github/workflows/on_push.yaml <(val='On Push' yq eval ".name = strenv(val)" .github/workflows/on_push.yaml))
patch .github/workflows/on_pull_request.yaml <<< $(\diff --color -U0 -w -b --ignore-blank-lines .github/workflows/on_pull_request.yaml <(val='On Pull Request' yq eval ".name = strenv(val)" .github/workflows/on_pull_request.yaml))

# Restore the whitespace lost after the `.name` attribute when doing the above patch method
sed -i 's/^name:.*$/&\n/' .github/workflows/on_push.yaml
sed -i 's/^name:.*$/&\n/' .github/workflows/on_pull_request.yaml

