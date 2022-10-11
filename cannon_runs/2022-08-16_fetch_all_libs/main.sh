#!/bin/env bash

# This script finds any charm directories (for single or multi charm repos) and then runs fetch-libs on each

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
  # explicitly add these as they might be .gitignored'd
  git add ./lib/charms/* -f
  cd -
done
