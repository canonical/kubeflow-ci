#!/usr/bin/env bash
set -x

# This script:
# * finds and bumps image versions in metadata.yamls if they fit a pattern
# * bumps image versions in the jupyter-ui spawner config
# * bumps image versions in the katib suggestions config

# Get the absolute path to where this script lives, so we can copy files
# from here without knowing that path ahead of runtime.
# Taken from https://stackoverflow.com/a/4774063/5394584
# Seems like there's cases where this might not work, but generally good?
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
echo "Copying source files from '$SCRIPTPATH'"

echo "I am executing this script from $(pwd)"

# Glob pattern to match all metadata.yaml files
METADATA_FILE_PATTERN="**/metadata.yaml"

# Kubeflow (matches any image using the standard kubeflow release versioning)
TAG_OLD_PATTERN="\([^:]*\):v1.6.0-rc.[0-9]\{1,\}"
TAG_NEW="\1:v1.6.0-rc.2"
find . -type f -wholename "$METADATA_FILE_PATTERN" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;
# Jupyter ui's spawner config
sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" ./charms/jupyter-ui/src/spawner_ui_config.yaml

# KFP
TAG_OLD_PATTERN="\(gcr.io\/ml-pipeline\/[^:]*\):2.0.0-alpha.[0-9]\{1,\}"
TAG_NEW="\1:2.0.0-alpha.3"
find . -type f -wholename "$METADATA_FILE_PATTERN" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;

# KServe
TAG_OLD_PATTERN="\(kserve\/[^:]*\):v[0-9]\{1,\}.[0-9]\{1,\}.[0-9]\{1,\}"
TAG_NEW="\1:v0.8.0"
find . -type f -wholename "$METADATA_FILE_PATTERN" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;

# Training Operator
TAG_OLD_PATTERN="\(kubeflow\/training-operator\):v[0-9]\{1,\}-[a-z0-9]\{1,\}"
TAG_NEW="\1:v1-e1434f6"
find . -type f -wholename "$METADATA_FILE_PATTERN" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;

# Katib
TAG_OLD_PATTERN="\(docker.io\/kubeflowkatib\/[^:]*\):v[0-9]\{1,\}.[0-9]\{1,\}.[0-9]\{1,\}-rc.[0-9]\{1,\}"
TAG_NEW="\1:0.14.0-rc.0"
find . -type f -wholename "$METADATA_FILE_PATTERN" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;
# Katib also has images in several JSON files
find . -type f -wholename "./charms/katib-controller/src/*.json" -exec sed -i "s/$TAG_OLD_PATTERN/$TAG_NEW/g" {} \;
