#!/usr/bin/env bash
#
# Replace ubuntu-latest with ubuntu-20.04 in workflows
#
find .github/workflows -name "*.yaml" -exec sed -i 's/juju-channel:.*/juju-channel: 3.6\/stable/g' {} \;
