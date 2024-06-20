#!/usr/bin/env bash
set -x

# This script:
# * finds all files named renovate.json within any subdirectory and replaces their contents with a predefined JSON content block.

# Get the absolute path to where this script lives, so we can copy files
# from here without knowing that path ahead of runtime.
# Taken from https://stackoverflow.com/a/4774063/5394584
# Seems like there's cases where this might not work, but generally good?
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
echo "Copying source files from '$SCRIPTPATH'"

RENOVATE_FILE_PATTERN="**/renovate.json"

echo "I am executing this script from $(pwd)"

# Find all renovate.json files recursively within the current directory and its subdirectories
find . -type f -wholename "$RENOVATE_FILE_PATTERN" | while read -r file; do
    # Replace the contents of each renovate.json file
    echo '{
    "$schema": "https://docs.renovatebot.com/renovate-schema.json",
    "extends": [
        "github>canonical/charmed-kubeflow-workflows"
    ]
}' > "$file"
    echo "Updated $file"
done
