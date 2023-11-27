#!/usr/bin/env bash
set -x

# This script:
# * finds requirements-lint.in files in the repo and it unpins the flake8 for each of them
# * removes specific pin comment
# * run pip compile for the requirements-lint.in

# Get the absolute path to where this script lives, so we can copy files
# from here without knowing that path ahead of runtime.
# Taken from https://stackoverflow.com/a/4774063/5394584
# Seems like there's cases where this might not work, but generally good?
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
echo "Copying source files from '$SCRIPTPATH'"

REQUIREMENTS_FILE_PATTERN="**/requirements-lint.in"

echo "I am executing this script from $(pwd)"

# Iterate through each requirements-lint.in file and replace the line with pinned falke8
find . -type f -wholename "$REQUIREMENTS_FILE_PATTERN" -exec sed -i 's/flake8<.*$/flake8/' {} \;
# Remove the flake8 pin comment 
find . -type f -wholename "$REQUIREMENTS_FILE_PATTERN" -exec sed -i '/^# Pinned because `flake8-copyright==0\.2\.3` is incompatible with `flake8>=6`\.  Can unpin this/,/^# when https:\/\/github\.com\/savoirfairelinux\/flake8-copyright\/pull\/20 or a similar fix is released/d' {} \;

tox --version

find . -type f -wholename "$REQUIREMENTS_FILE_PATTERN" | while read -r path; do
    directory=$(dirname "$path")
    file=$(basename "$path")

    cd $directory
    # Run pip-compile for each requirements-lint.in file
    pip-compile --resolver=backtracking -U "$file"
    echo "Generated requirements-lint.txt for $path"
    cd -
done
