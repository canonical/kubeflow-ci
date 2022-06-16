import json
import logging
import yaml
import os

import requests

GITHUB_API_URL = "https://api.github.com"
DEFAULT_REPO_OWNER = "Canonical"
MAIN_BRANCH_NAMES = ["main", "master"]

headers = {"content-type": "application/vnd.github.v3+json"}
logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def trim_charmcraft_dict(full_bundle_dict):
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
    # TODO: add releases or not
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), release_directory))

    if os.path.isdir(path):
        files = os.listdir(path)
        yaml_files = [file for file in files if file.endswith(".yaml")]
        # use yaml to parse each file
        result = {}
        for yaml_file_name in yaml_files:
            with open(os.path.join(path, yaml_file_name), "r") as file:
                file_content = yaml.safe_load(file)
                result = {**result, **trim_charmcraft_dict(file_content)}

        return result
    else:
        raise Exception(f"Cannot proceed with script. Failed to find directory {path}")


def get_latest_commit_sha(github_repo_name, github_repo_owner=DEFAULT_REPO_OWNER):
    latest_sha = ""
    for main_branch_name in MAIN_BRANCH_NAMES:
        get_ref_api = f"{GITHUB_API_URL}/repos/{github_repo_owner}/{github_repo_name}/git/ref/heads/{main_branch_name}"
        res = requests.get(get_ref_api)
        if res.status_code == 200:
            body = res.json()
            latest_sha = body["object"]["sha"]
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
    parse_yamls("../releases/1.4")
    # check git diff if release directory was not provided
    print("Hello world")
