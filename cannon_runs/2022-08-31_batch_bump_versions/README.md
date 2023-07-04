# Summary 
The purpose of this batch operation is to bump versions of some of our common images, typically like when we bump from one release candidate to another. To use, modify the tag patterns in `main.sh` to handle the previous/new tagging.

# Execution details

This is a batch update to our repos completed using [git-xargs](https://github.com/gruntwork-io/git-xargs).  Execution was completed using commands listed in `run_git-xargs.sh`.

`git-xargs` executes the script you provide to modify one or more repos.  It:
* pulls each repo
* executes the provided script in the root dir of each repo
* creates PRs for each change
* tries to handle rate limiting issues from GitHub

