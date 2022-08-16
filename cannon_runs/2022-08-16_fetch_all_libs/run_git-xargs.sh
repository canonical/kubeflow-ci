# Build env needed for the script

# Execute
# during testing, use:
#   --loglevel DEBUG --dry-run --draft\
# NOTE: The script path passed as the positional arg below must be absolute, not relative
git-xargs \
  --repos repos.txt \
  --branch-name 2022-08-16-bump-libs \
  --pull-request-title "chore: bump all charm libs" \
  --no-skip-ci \
  bash /home/scribs/code/canonical/kubeflow-ci/add-fetch-libs-git-xargs/cannon_runs/2022-08-16_fetch_all_libs/main.sh
