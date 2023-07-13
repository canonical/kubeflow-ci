#!/usr/bin/bash
#
# This script parses given bundle file for github repositories and branches. Then checks out each
# charm's repository one by one using specified branch and collects images referred by that charm
# using that repository's image collection script
#
BUNDLE_FILE=$1
IMAGES=()
REPOS_BRANCHES=($(yq -r '.applications[] | to_json' $BUNDLE_FILE | jq -r 'select(._github_repo_name) | "\(._github_repo_name):\(._github_repo_branch)"' | sort --unique))
for REPO_BRANCH in "${REPOS_BRANCHES[@]}"; do
  IFS=: read -r REPO BRANCH <<< "$REPO_BRANCH"
  git clone https://github.com/canonical/$REPO
  cd $REPO
  git checkout -b tmp $BRANCH
  IMAGES+=($(bash ./tools/get-images.sh))
  cd - > /dev/null
done
printf "%s\n" "${IMAGES[@]}"
