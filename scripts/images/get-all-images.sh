#!/usr/bin/bash
BUNDLE_FILE=$1
RELEASE=$2
IMAGES=()
REPOS=($(grep _github_repo_name $BUNDLE_FILE | awk '{print $2}' | sort --unique))
for REPO in "${REPOS[@]}"; do
  git clone https://github.com/canonical/$REPO
  # get charm's images from metadata
  cd $REPO
  IMAGES+=($(get-metadata-images.sh))
  cd -
  # get workload images
  IMAGES+=($($REPO/tools/get-images-$RELEASE.sh))
done
printf "%s\n" "${IMAGES[@]}"
