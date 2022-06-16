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
GITHUB_TOKEN_NAME = "KUBEFLOW_BOT_TOKEN"

HEADERS = {"content-type": "application/vnd.github.v3+json"}
logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def get_git_diff():
    """() -> [str]
    Return a list of file paths of files changed in the last commit
    """
    cur_repo = Repo.init(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    diff = cur_repo.git.diff("HEAD~1..HEAD", name_only=True).split("\n")
    return diff


def get_modified_releases_dirs(git_diff_file_paths):
    """([str]) -> set(str)
    Takes list of file paths as input, returns a list of releases directory path.
    """
    release_dir_name = "releases"
    result = []
    for file_path in git_diff_file_paths:
        splitted = file_path.split("/")
        if splitted[0] == release_dir_name and splitted[-1].endswith(".yaml"):
            # dir path relative to this file
            result.append(f"../{release_dir_name}/{splitted[1]}")
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
    { "<charm_name>": {"version": str, "_github_repo_name": str }}
    Exception is raised if the directory does not exists
    """
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
            yaml_file_path = os.path.join(path, yaml_file_name)
            logger.info(f"Parsing charms in yaml `{yaml_file_path}`")
            with open(yaml_file_path, "r") as file:
                file_content = yaml.safe_load(file)
                result = {**result, **trim_charmcraft_dict(file_content)}
        logger.info(f"Finished parsing yamls in `{release_directory}`.")
        logger.info(f"Resulting charms info: {result}")
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
        res = requests.get(get_ref_api, headers=HEADERS)
        if res.status_code == 200:
            body = res.json()
            latest_sha = body["object"]["sha"]
            logger.info(
                f"func get_latest_commit_sha: Found latest commit SHA `{latest_sha}` for repository `{github_repo_name}` in branch `{main_branch_name}`"
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
    r = requests.post(
        create_ref_api,
        data=json.dumps(payload),
        headers={
            **HEADERS,
            "Authorization": f"Token {os.environ.get(GITHUB_TOKEN_NAME)}",
        },
    )
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


def branch_creation_automation(release_path):
    """(str) -> None
    Release directory path relative to this file as input
    e.g. "../releases/1.4"
    """
    charms_info = parse_yamls(release_path)
    for charm in charms_info:
        logger.info(f"Start creating branch for charm `{charm}`")
        create_git_branch(
            charms_info[charm]["_github_repo_name"],
            f"track/{charms_info[charm]['version']}",
        )


if __name__ == "__main__":
    if not os.environ.get(GITHUB_TOKEN_NAME):
        logger.error(
            f"Failed to find env var `{GITHUB_TOKEN_NAME}`. Unable to create branches without it."
        )
        sys.exit()
    if len(sys.argv) == 1:
        git_diff = get_git_diff()
        release_changes = get_modified_releases_dirs(git_diff)
        for release_path in release_changes:
            branch_creation_automation(release_path)
    # for manually triggered runs
    elif len(sys.argv) == 2:
        branch_creation_automation(sys.argv[1])
    else:
        logger.error("Specified too many arguments. Script exited.")
