#!/usr/bin/env bash
set -x

# This script:
# * appends metadata generation code to tox.ini file
echo "

# images managed by charm(s)
[testenv:metadata-images]
allowlist_externals =
  bash
  git
commands = |
        git clone --branch kf-3783-feat-metatdata-images https://github.com/canonical/kubeflow-ci.git
        bash -c 'bash ./scripts/images/get-metadata-images.sh '\>' > metadata-images.txt && cat metadata-images.txt'
" >> tox.ini
