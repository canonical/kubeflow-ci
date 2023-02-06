# Summary
The purpose of this batch operation is to pin ubuntu version of some of our repositories to version 20.04.

# Execution details

This is a batch update to our repos completed using git-xargs. Execution was completed using commands listed in run_git-xargs.sh.

git-xargs executes the script you provide to modify one or more repos. It:

- pulls each repo
- executes the provided script in the root dir of each repo
- creates PRs for each change
- tries to handle rate limiting issues from GitHub
