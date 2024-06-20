### Generate repos.txt
```bash
gh search repos --topic charmed-kubeflow --limit 200 --json fullName | jq -r ".[].fullName" > repos.txt
```

### Testing locally
Use the `git-xargs-runner-dev.sh` script, which will
1. Call the `repo-modifier.sh` script
2. Only for the `bundle-kubeflow` repo
3. Keep the cloned repo in `/tmp` for further debugging
