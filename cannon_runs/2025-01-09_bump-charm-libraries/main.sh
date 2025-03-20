#!/usr/bin/env bash
# This script finds any charm directories (for single or multi charm repos) and then runs fetch-libs on each
# Epanded https://github.com/canonical/kubeflow-ci/blob/main/cannon_runs/2022-08-16_fetch_all_libs/main.sh
# to also check for major version bumps and commit a `do-not-merge-message.txt` file if there is one.

CHARMS_DIR="./charms"

if [ -d "$CHARMS_DIR" ];
then
  CHARM_PATHS=$(find $CHARMS_DIR -maxdepth 1 -type d -not -path '*/\.*' -not -path "$CHARMS_DIR")
else
  if [ -f "./metadata.yaml" ]
  then
    CHARM_PATHS="./"
  else
    echo "Cannot find valid charm directories - aborting"
    exit 1
  fi
fi

for d in $CHARM_PATHS; do
    echo "Operating on charm dir '$d'"
    cd $d
    # This was used to add some missing libs in a few cases, but not useful for 
    # a general fetch-libs batch run
    # charmcraft fetch-lib charms.observability_libs.v0.juju_topology
    charmcraft fetch-lib
    OUTPUT="$(noctua charm libraries check --major)"
    if [ -n "$OUTPUT" ];
    then
        echo 'There is a new major version for:' > do-not-merge-message.txt
        echo $OUTPUT >> do-not-merge-message.txt
    fi
    # explicitly add these as they might be .gitignored'd
    git add ./lib/charms/* -f
    cd -
done
