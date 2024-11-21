# Build env needed for the script
python -m venv venv
source venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

# Execute
# during testing, use --dry-run --loglevel DEBUG, then --draft
git-xargs \
  --repos repos.txt \
  --branch-name add-publish-on-click-from-branch-test-script \
  --pull-request-title "feat: Enable publish-on-click from any branch" \
  --commit-message 'Allows the publish.yaml `workflow_dispatch` to be run using any branch in this repo.  See [this test repo](https://github.com/ca-scribner/test-charm/blob/main/.github/workflows/publish.yaml) for the updated action.  You can run_workflow [here](https://github.com/ca-scribner/test-charm/actions/workflows/publish.yaml) with an optional github branch argument.  To demonstrate that it worked, [this branch `another-branch`](https://github.com/ca-scribner/test-charm/tree/another-branch), which has the file `src/file-on-branch-only` was promoted from the branch in [this action run](https://github.com/ca-scribner/test-charm/actions/runs/2863188096) to `latest/candidate`, which can be confirmed through `juju download ca-scribner-test-charm --channel latest/candidate`' \
  --no-skip-ci \
  python /home/scribs/code/canonical/git-xargs-runs/add-publish-script/main.py
