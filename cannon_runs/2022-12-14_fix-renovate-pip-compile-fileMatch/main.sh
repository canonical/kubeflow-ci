#!/usr/bin/env bash
set -x

# This script:
# * finds and bumps all uses of github actions from `canonical/charming-actions` to v2.1.1.  

echo "Script is executing from $(pwd)"

FILEMATCH='["(^|/)requirements\\.in$", "(^|/)requirements-fmt\\.in$", "(^|/)requirements-lint\\.in$", "(^|/)requirements-unit\\.in$", "(^|/)requirements-integration\\.in$", "(^|/)requirements.*\\.in$"]'

cat renovate.json |  jq --indent 4 --argjson filematch "$FILEMATCH" '."pip-compile".fileMatch |= $filematch' > renovate.json.tmp && mv renovate.json.tmp renovate.json
