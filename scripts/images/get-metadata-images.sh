#!/bin/bash
# get charm's images from metadata
IMAGES=()
IMAGES=($(find $REPO -type f -name metadata.yaml -exec yq '.resources | to_entries | .[] | .value | ."upstream-source"' {} \;))
printf "%s\n" "${IMAGES[@]}"
