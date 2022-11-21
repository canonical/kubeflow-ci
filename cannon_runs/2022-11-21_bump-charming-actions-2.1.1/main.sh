#!/usr/bin/env bash
set -x

# This script:
# * finds and bumps all uses of github actions from `canonical/charming-actions` to v2.1.1.  

echo "Script is executing from $(pwd)"

YAML_FILE_PATTERN="*.yaml"
CHARMING_ACTIONS_PATTERN="canonical\/charming-actions\/\([^@]*\)@.*$"
CHARMING_ACTIONS_NEW_TEXT="canonical\/charming-actions\/\1@2.1.1"

find .github/workflows -type f -wholename "$YAML_FILE_PATTERN" -exec sed -i "s/$CHARMING_ACTIONS_PATTERN/$CHARMING_ACTIONS_NEW_TEXT/" {} \;
