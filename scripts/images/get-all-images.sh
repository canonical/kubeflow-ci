#!/usr/bin/bash
BUNDLE_FILE=$1
RELEASE=$2
IMAGES=()
REPOS=($(grep _github_repo_name $BUNDLE_FILE | awk '{print $2}' | sort --unique))
for REPO in "${REPOS[@]}"; do
  git clone https://github.com/canonical/$REPO
  cd $REPO
  if test -f "./tools/get-images-$RELEASE.sh"; then
    IMAGES+=($(./tools/get-images-$RELEASE.sh))
  fi
  cd - > /dev/null
done
printf "%s\n" "${IMAGES[@]}"
