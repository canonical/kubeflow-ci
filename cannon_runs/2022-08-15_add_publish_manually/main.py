from pathlib import Path
import shutil
from typing import Union

from ruamel.yaml import YAML


def main():
    """
    Script to edit a git repo, for use with git-xargs

    This script:
    * creates get-charm-paths.sh and publish.yaml
    * patches on_push.yaml and on_pull_request.yaml to pass credentials with a different name
    """
    createOrReplaceFile(
        source="./data/get-charm-paths.sh",
        target=".github/workflows/get-charm-paths.sh",
    )
    createOrReplaceFile(
        source="./data/publish.yaml", target=".github/workflows/publish.yaml"
    )

    # For each of on_push and on_pull_request, do:
    # Rename .jobs.publish-charm.secrets.charmcraft-credentials to .jobs.publish-charm.secrets.CHARMCRAFT_CREDENTIALS
    # Simplify workflow names
    yaml = YAML(typ="rt")

    workflows_to_patch = [
        (".github/workflows/on_push.yaml", "On Push"),
        (".github/workflows/on_pull_request.yaml", "On Pull Request"),
    ]

    for workflow_file, workflow_name in workflows_to_patch:
        patch_workflow(filename=workflow_file, workflow_name=workflow_name)


def load_save_yaml(func):
    """A decorator that will load a yaml file, pass content to func, then save the yaml after"""

    def loading_wrapper(*args, filename=None, **kwargs):
        if filename is None:
            raise ValueError(f"filename must be specified.  Got {filename}")

        # Load preserving comments and whitespace
        yaml = YAML(typ="rt")

        with open(filename, "r") as fin:
            data = yaml.load(fin)

        data = func(data=data, *args, **kwargs)

        with open(filename, "w") as fout:
            yaml.dump(data, fout)

    return loading_wrapper


def createOrReplaceFile(source: Union[str, Path], target: Union[str, Path]):
    """Replaces target with source, creating the new file if target does not exist.

    Params:
        source: A absolute or relative file to be copied.  If source is relative,
                it will be interpreted as relative to THIS SCRIPT's LOCATION not
                where it is called from, because this script will be used remotely.
        target: A path to a file relative to the CALLING LOCATION, not this script's
                location.
    """
    source = Path(source)
    target = Path(target)

    if source.is_absolute() is False:
        # Make source relative to this calling script's location
        parent = Path(__file__).parent.resolve()

        source = parent / source

    if target.is_absolute():
        raise ValueError(f"Target must be a relative path.  Got {target}")

    shutil.copyfile(source, target)


@load_save_yaml
def patch_workflow(data: dict, workflow_name):
    """
    Patches a yaml dict to refactor secret and rename the top level name
    """
    data["name"] = workflow_name

    data["jobs"]["publish-charm"]["secrets"]["CHARMCRAFT_CREDENTIALS"] = data["jobs"][
        "publish-charm"
    ]["secrets"]["charmcraft-credentials"]
    del data["jobs"]["publish-charm"]["secrets"]["charmcraft-credentials"]

    return data


if __name__ == "__main__":
    main()
