#!/usr/bin/env bash
#
# Replace ubuntu-latest with ubuntu-20.04 in workflows
#
find .github/workflows -name "*.yaml" -exec sed -i 's/runs-on: ubuntu-latest/runs-on: ubuntu-20.04/g' {} \;
