# Add docstring for each functions
# add description on how to use it, and any gotchas
import json
import logging
import os
import sys

import requests
import yaml
from git import Repo

GITHUB_API_URL = "https://api.github.com"
DEFAULT_REPO_OWNER = "canonical"
MAIN_BRANCH_NAMES = ["main", "master"]

headers = {"content-type": "application/vnd.github.v3+json"}
logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def get_git_diff():
    cur_repo = Repo.init(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    print(
        f"DEBUGGING ~ file: branch_track_creation.py ~ line 24 ~ cur_repo.git.diff(HEAD~1..HEAD, name_only=True): {cur_repo.git.diff('HEAD~1..HEAD', name_only=True)}"
    )
    diff = cur_repo.git.diff("HEAD~1..HEAD", name_only=True).split("\n")
    print(f"DEBUGGING ~ file: branch_track_creation.py ~ line 24 ~ diff: {diff}")
    result = []
    for file_path in diff:
        splitted = file_path.split("/")
        # check for duplicate
        if splitted[0] == "releases":
            result.append(splitted[1])
    return set(result)


def trim_charmcraft_dict(full_bundle_dict):
    """(dict) -> dict or Exception
    Take a dictionary following the charmcraft yaml format and return
    a dictionary with only information needed for the script.
    Charms with `latest` in channel or missing `_github_repo_name` would
    be skipped and not included in the return dictionary.
    The function would raise an exception if it misses key fields
    in the yaml
    { "<app_name>": {"version": str, "_github_repo_name": str }}
    """
    result = {}
    try:
        if full_bundle_dict["applications"]:
            for app_name in full_bundle_dict["applications"]:
                app_dict = full_bundle_dict["applications"][app_name]

                if (
                    "latest" in app_dict["channel"]
                    or not "_github_repo_name" in app_dict
                ):
                    continue

                result[app_dict["charm"]] = {
                    "version": app_dict["channel"].split("/")[0],
                    "github_repo_name": app_dict["_github_repo_name"],
                }
            return result
    except:
        raise Exception(
            "Unexpecting yaml format. Expected `.applications`, `.applications.<app_name>.charm` and `.applications.<app_name>.channel` keys in yaml but failed to find."
        )


def parse_yamls(release_directory):
    """(str) -> dict or Exception
    Takes the path of directory as input (path relative to the location of this file),
    returns a dictionary
    { "<app_name>": {"version": str, "_github_repo_name": str }}
    Exception is raised if the directory does not exists
    """
    # TODO: add releases or not
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), release_directory))

    if os.path.isdir(path):
        yaml_files = [
            file_name for file_name in os.listdir(path) if file_name.endswith(".yaml")
        ]
        # use yaml to parse each file
        if not yaml_files:
            logger.warning(
                f"func parse_yamls: No yamls files are present in directory `{path}`"
            )
        result = {}
        for yaml_file_name in yaml_files:
            with open(os.path.join(path, yaml_file_name), "r") as file:
                file_content = yaml.safe_load(file)
                result = {**result, **trim_charmcraft_dict(file_content)}

        return result
    else:
        raise Exception(f"Cannot proceed with script. Failed to find directory {path}")


def get_latest_commit_sha(github_repo_name, github_repo_owner=DEFAULT_REPO_OWNER):
    """(str, str) -> str
    Loop through possible main branch names. Returns the first commit sha found.
    """
    latest_sha = ""
    for main_branch_name in MAIN_BRANCH_NAMES:
        get_ref_api = f"{GITHUB_API_URL}/repos/{github_repo_owner}/{github_repo_name}/git/ref/heads/{main_branch_name}"
        res = requests.get(get_ref_api)
        if res.status_code == 200:
            body = res.json()
            latest_sha = body["object"]["sha"]
            logger.info(
                f"func get_latest_commit_sha: Found latest commit SHA for repository `{github_repo_name}` in branch `{main_branch_name}`"
            )
            break
    return latest_sha


def create_git_branch(
    github_repo_name, new_branch_name, github_repo_owner=DEFAULT_REPO_OWNER
):
    """(str, str, str) -> None
    It creates the git branch using github api.
    This function should NEVER raise an exception.
    Success and error results are communicated through the logger.
    """
    latest_sha = get_latest_commit_sha(
        github_repo_name, github_repo_owner=github_repo_owner
    )
    if not latest_sha:
        logger.error(
            f"func create_git_branch: Failed to get latest sha from branch main or master for repository named {github_repo_name}. Branch {new_branch_name} is not created. Please check if the repository name is correct."
        )
        return
    create_ref_api = (
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{github_repo_name}/git/refs"
    )
    payload = {"ref": f"refs/heads/{new_branch_name}", "sha": latest_sha}
    # TODO: github auth token
    r = requests.post(create_ref_api, data=json.dumps(payload))
    if r.status_code == 201:
        logger.info(
            f"func create_git_branch: Branch `{new_branch_name}` is successfully created for repository `{github_repo_name}`"
        )
    elif r.status_code == 422:
        logger.info(
            f"func create_git_branch: Branch `{new_branch_name}` already exists in repository `{github_repo_name}`"
        )
    else:
        logger.info(
            f"func create_git_branch: Something went wrong. Failed to create branch `{new_branch_name}` in repository `{github_repo_name}`. Check if authorization token is provided"
        )


if __name__ == "__main__":
    # parse_yamls("../releases/1.4")
    # check git diff if release directory was not provided
    create_git_branch("natasha-dummy-charm", "featureA", "agathanatasha")
