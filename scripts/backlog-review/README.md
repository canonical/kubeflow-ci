# Summary

These scripts and instructions are for making it easier to review the issue backlog for the Charmed Kubeflow team.  This script helps break the backlog up into chunks that can be actioned by each team member.

# Usage

* export a JSON file of the open issues from all Charmed Kubeflow repositories:
  * `gh repo list canonical --topic charmed-kubeflow --json name,issues > repo_open_issues.json` 
* split the issues into N roughly equal groups:
  * `python group_issues.py repo_open_issues.json N`
* assign each person a group!
