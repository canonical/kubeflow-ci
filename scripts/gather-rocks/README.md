# Gather the rocks maintained by a team

`gather_rocks.py` scans the GitHub repositories of a user, an organization, or an organization's team for rocks (`rockcraft.yaml` files). For each rock, it works out the registry and the name it is published under, and checks that the image exists in that registry.

## Requirements
Python 3.12 or newer.
```bash
pip install -r requirements.txt
```

The script needs a GitHub token, passed with `--github-token` or the `GITHUB_TOKEN` environment variable, for example `GITHUB_TOKEN=$(gh auth token)`:
* To list and read the repositories, a token with read access is needed.
* To read the `ROCK_IMAGE_REGISTRY` Actions variables, the token needs collaborator access to the repositories: a classic token with the `repo` scope, or a fine-grained token with read access to "Variables". Without it, the script logs a warning and falls back to the `--default-registry`.

No registry credentials are needed, since images are checked anonymously. This means that private images are reported as missing.

## Usage
```bash
# All the repositories of a team
python3 gather_rocks.py --owner canonical/mlops

# All the repositories of an organization or a user
python3 gather_rocks.py --owner canonical
```

| Option | Description |
| --- | --- |
| `--owner` | `<user\|organization>` to scan all its repositories, or `<organization>/<team>` to scan the repositories of a team, e.g. `canonical/mlops`. |
| `--github-token` | GitHub token, defaults to the `GITHUB_TOKEN` environment variable. |
| `--include-archived` | Also scan archived repositories, which are skipped by default. |
| `--skip-tags` | Only check that the images exist, without gathering their tags. |
| `--default-registry` | Registry used when it cannot be found for a rock, `docker.io/charmedkubeflow` by default. |
| `--output-format` | `table` (default), `simple`, `json`, `yaml` or `csv`. `simple` writes one image per line, with its latest tag if tags were gathered. `json` and `yaml` also include the list of tags of each rock. |
| `--output-file` | File to write the output to, instead of stdout. Logs are always written to stderr. |
| `--workers` | Number of repositories and images to check in parallel, 8 by default. |
| `--verbose` | Log debug messages. |

The `ERROR` column shows the problems found with each rock, which are also logged:
* `Image not found in the registry, or private`: the image does not exist in the registry it should be published to.
* `No tag for version <version>` (unless `--skip-tags` is set): the image exists, but has no tag for the version of its `rockcraft.yaml`.
* GitHub, registry, or `rockcraft.yaml` errors met while inspecting the rock.

These problems, like repositories that could not be scanned, are reported without failing the run. The script only exits with `1` if it cannot run at all, e.g. when the repositories of the owner cannot be listed.

Example output, trimmed:
```
REPOSITORY              PATH                IMAGE                                         VERSION  TAG COUNT  LATEST TAG                     ERROR
canonical/envoy-rock    1.28.2              ghcr.io/canonical/envoy                       1.28.2   10         1.28.2-ck8                     -
canonical/kserve-rocks  controller          docker.io/charmedkubeflow/kserve-controller   0.17.0   9          0.17.0-f871557-20261101031608  -
canonical/kserve-rocks  tensorflow-serving  docker.io/charmedkubeflow/tensorflow-serving  v2.6.2   1          2.6.2-3f1565f                  -
canonical/kserve-rocks  tritonserver        ghcr.io/canonical/tritonserver                23.05    11         23.05-9946fc8-20261110145148   -
```

The same rocks with `--output-format simple`, e.g. to pass the images to another tool:
```
ghcr.io/canonical/envoy:1.28.2-ck8
docker.io/charmedkubeflow/kserve-controller:0.17.0-f871557-20261101031608
docker.io/charmedkubeflow/tensorflow-serving:2.6.2-3f1565f
ghcr.io/canonical/tritonserver:23.05-9946fc8-20261110145148
```
Images are written without a tag when tags are skipped, or when the image has no tag for the version of its rock. Rocks whose image is unknown because of an error are left out, and the error is logged.

## How it works

### Finding the rocks
The script lists the repositories of the owner, skipping archived ones unless `--include-archived` is set. For each repository, it lists all the files of the default branch with a single request to the [Git trees API](https://docs.github.com/en/rest/git/trees), and every `rockcraft.yaml` is a rock. This finds rocks wherever they are, e.g. at the root of a repository, in sub-directories, or in repositories whose name does not contain "rock". GitHub truncates the file tree of very large repositories, in which case the script logs a warning.

The name and the version of each rock are read from its `rockcraft.yaml`.

### Where a rock is published
The registry of each rock is found the same way the publishing workflows do, using the first of:
1. `ghcr.io/<owner>`, if the repository uses the [k8s-workflows](https://github.com/canonical/k8s-workflows) `build_rocks.yaml`.
2. The `registry` in the `rock-ci-metadata.yaml` next to the `rockcraft.yaml`, used by the [charmed-kubeflow-workflows](https://github.com/canonical/charmed-kubeflow-workflows) to override the registry of a rock.
3. The `ROCK_IMAGE_REGISTRY` Actions variable of the repository, used by the charmed-kubeflow-workflows.
4. The `ROCK_IMAGE_REGISTRY` Actions variable of the organization, if it is shared with the repository.
5. The `--default-registry`.

The image is then `<registry>/<rock name>`, e.g. `docker.io/charmedkubeflow/kserve-controller`.

### Checking the images
* Docker Hub images are checked with the [Docker Hub API](https://docs.docker.com/reference/api/hub/latest/), because its registry API cannot tell missing images apart from private ones.
* Images in other registries, e.g. `ghcr.io`, are checked with the [OCI distribution API](https://github.com/opencontainers/distribution-spec/blob/main/spec.md), using anonymous tokens.

Unless `--skip-tags` is set, the script gathers the tags of each image that belong to the version of its rock, i.e. `<version>` or `<version>-*`, and reports how many there are and the latest one. A `v` in front of the version number is ignored, so the version `v2.6.2` matches the tag `2.6.2-3f1565f`, and the other way around. Tags with a build timestamp suffix (`-YYYYMMDDhhmmss`, as created by the charmed-kubeflow-workflows) are ordered by it.

Docker Hub limits anonymous API requests to 180 per window per IP. When gathering tags, the existence of an image is deduced from its tags, so that each image takes a single request. Requests that are rate limited are retried automatically.

## Tests
```bash
tox -e test_gather_rocks
```

The test dependencies are in `requirements-test.in`, which includes the script's `requirements.txt`. To update the pinned versions, run `pip-compile --strip-extras requirements.in` and then `pip-compile --strip-extras requirements-test.in` from this directory, with Python 3.12.
