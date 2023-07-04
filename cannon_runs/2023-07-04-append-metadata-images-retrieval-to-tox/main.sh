#!/usr/bin/env bash
set -x

# This script:
# * appends metadata generation code to tox.ini file
echo "
# images managed by charm(s)
[testenv:metadata-images]
allowlist_externals =
  bash
  jq
  yq
commands = bash -c 'find . -type f -name metadata.yaml -exec yq '\''.resources | to_entries'\[''\]'.value'\''  '\{''\}' \'\;' | jq -r '\''.\"upstream-source\"'\'' '\>' metadata-images.txt && cat metadata-images.txt'
" >> tox.ini
