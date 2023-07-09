#!/usr/bin/bash
BUNDLE_FILE=$1
IMAGES=()
REPOS=($(grep _github_repo_name $BUNDLE_FILE | awk '{print $2}' | sort --unique))
for REPO in "${REPOS[@]}"; do
  git clone https://github.com/canonical/$REPO
  # get charm's images from metadata
  IMAGES+=($(find $REPO -type f -name metadata.yaml -exec yq '.resources | to_entries[].value'  {} \; | jq -r '."upstream-source"'))
  # get workload images
  #IMAGES+=($($REPO/tools/get-images.sh))
done
