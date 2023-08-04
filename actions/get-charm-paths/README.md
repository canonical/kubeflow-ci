# Summary

This action emits a JSON list of the relative paths to any Juju Charms in this directory.

# Example usage

Example workflow:

```yaml
name: Demo get-charm-paths

on:
  workflow_dispatch:

jobs:
  get-charm-paths:
    name: Generate the Charm Matrix content
    runs-on: ubuntu-latest
    outputs:
      charm_paths: ${{ steps.get-charm-paths.outputs.charm-paths }}
    steps:
      - uses: actions/checkout@v2
        with:
          fetch-depth: 0
      - name: Get paths for all charms in this repo
        id: get-charm-paths
        uses: canonical/kubeflow-ci/actions/get-charm-paths@main

  echo-charm-paths:
    name: Echo charm paths emitted
    runs-on: ubuntu-latest
    needs: get-charm-paths
    steps:
      - run: |
          echo "Got charm_paths: ${{ needs.get-charm-paths.outputs.charm_paths }}"

  use-charm-paths:
    name: Use charm paths in a matrix
    runs-on: ubuntu-latest
    needs: get-charm-paths
    strategy:
      fail-fast: false
      matrix:
        charm-path: ${{ fromJson(needs.get-charm-paths.outputs.charm_paths) }}
    steps:
      - run: |
          echo "Got charm path: ${{ matrix.charm-path }}"
```
