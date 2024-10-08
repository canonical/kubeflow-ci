#!/usr/bin/bash
#
# This script parses given bundle file for github repositories and branches. Then checks out each
# charm's repository one by one using specified branch and collects images referred by that charm
# using that repository's image collection script
#
set -xe

BUNDLE_FILE=$1
IMAGES=()
# retrieve all repositories and branches for CKF
REPOS_BRANCHES=($(yq -r '.applications[] | to_json' $BUNDLE_FILE | jq -r 'select(._github_repo_name) | "\(._github_repo_name):\(._github_repo_branch)"' | sort --unique))

for REPO_BRANCH in "${REPOS_BRANCHES[@]}"; do
  IFS=: read -r REPO BRANCH <<< "$REPO_BRANCH"
  git clone --branch $BRANCH https://github.com/canonical/$REPO
  cd $REPO
  IMAGES+=($(bash ./tools/get-images.sh))
  cd - > /dev/null
  rm -rf $REPO
done

# retrieve all repositories and branches for dependencies
DEP_REPOS_BRANCHES=($(yq -r '.applications[] | to_json' $BUNDLE_FILE | jq -r 'select(._github_dependency_repo_name) | "\(._github_dependency_repo_name):\(._github_dependency_repo_branch)"' | sort --unique))

for REPO_BRANCH in "${DEP_REPOS_BRANCHES[@]}"; do
  IFS=: read -r REPO BRANCH <<< "$REPO_BRANCH"
  git clone --branch $BRANCH https://github.com/canonical/$REPO
  cd $REPO
  # for dependencies only retrieve workload containers from metadata.yaml
  IMAGES+=($(find -type f -name metadata.yaml -exec yq '.resources | to_entries | .[] | .value | ."upstream-source"' {} \;))
  cd - > /dev/null
  rm -rf $REPO
done

printf "%s\n" "${IMAGES[@]}"
