#!/usr/bin/bash
find . -type f -name metadata.yaml -exec yq '.resources | to_entries[].value'  {} \; | jq -r '."upstream-source"'
