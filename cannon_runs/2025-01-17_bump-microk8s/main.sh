#!/usr/bin/env bash
#
# Replace ubuntu-latest with ubuntu-20.04 in workflows
#
find .github/workflows -name "*.yaml" -exec sed -i 's/1.29-strict\/stable/1.31-strict\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.29\/stable/1.31\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.26-strict\/stable/1.31-strict\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.26\/stable/1.31\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.24-strict\/stable/1.31-strict\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.24\/stable/1.31\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.25-strict\/stable/1.31-strict\/stable/g' {} \;
find .github/workflows -name "*.yaml" -exec sed -i 's/1.25\/stable/1.31\/stable/g' {} \;
