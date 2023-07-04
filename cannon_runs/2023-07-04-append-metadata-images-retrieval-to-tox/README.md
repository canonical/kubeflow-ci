# Summary 
The purpose of this batch is to append a command to tox.ini that retrives list of container images from metadata.yaml and stores them in images.txt

# Execution details

This is a batch update to our repos completed using [git-xargs](https://github.com/gruntwork-io/git-xargs).  Execution was completed using commands listed in `run_git-xargs.sh`.

`git-xargs` executes the script you provide to modify one or more repos.  It:
* pulls each repo
* executes the provided script in the root dir of each repo
* creates PRs for each change
* tries to handle rate limiting issues from GitHub

