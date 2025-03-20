#!/usr/bin/env bash
#
# Replace ubuntu-latest with ubuntu-20.04 in workflows
#
find . -name "tox.ini" -exec sed -i 's/pip-tools/pip-tools\n    \# Pin due to https\:\/\/github.com\/jazzband\/pip-tools\/issues\/2131\n    pip==24.2/g' {} \;
find . -name "requirements*.txt" -type f -exec rm -f {} +
tox -e update-requirements
