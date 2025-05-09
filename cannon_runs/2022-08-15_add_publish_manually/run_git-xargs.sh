# Build env needed for the script
python -m venv venv
source venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

# Execute
# during testing, use --dry-run --loglevel DEBUG, then --draft
git-xargs \
  --repos repos.txt \
  --branch-name add-generic-publish-on-click \
  --pull-request-title "feat: Add generic, clickable publish.yaml" \
  --commit-message "Adds a generic publish.yaml that can be triggered through the UI" \
  --no-skip-ci \
  python /home/scribs/code/canonical/git-xargs-runs/add-publish-script/main.py
