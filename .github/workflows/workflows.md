
# sync_charmstore_credentials.yaml

This workflow automates updating charmstore/charmcraft credentials on all repos listed in `sync_charmstore_credentials.yaml`.  To add new managed repos, add them to the list in the yaml file.

To enable access to update the secrets of the above repos, a github PAT that has access to all repos must be stored here as a secret.  

To refresh the credentials for repos, do:

1. Get recent credentials, for example using:

(charmstore)
```
charm login && cat ~/.go-cookies
```
(charmcraft (requires charmcraft > 1.3.1)
```
charmcraft login --export --ttl 15000000 /tmp/charmcraft.credentials && echo "Copy the key below this line" && cat /tmp/charmcraft.credentials && rm /tmp/charmcraft.credentials
```

2. Insert above credentials into this repo's CHARMSTORE_CREDENTIAL/CHARMCRAFT_CREDENTIALS secret (Settings->Secrets)
3. Run the workflow (Actions->Sync Charmstore Credentials->Run workflow (button at the top right of the workflow runs list)).  To do a dryrun, leave dryrun=True.  To actually push secrets to all repos, set dryrun=False.

# sync_github_token.yaml

This workflow syncs the GitHub credentials used by the charm and rock CI workflows to all repos listed in `sync_github_token.yaml`.

The secrets synced are:

* `GH_TOKEN` - a Github PAT used by the CI workflows to open PRs and push branches.
* `GH_USER_EMAIL` - the email address of the account owning `GH_TOKEN`, used as the git committer email when signing commits (see [integrate-rock.yaml](https://github.com/canonical/charmed-kubeflow-workflows/blob/main/.github/workflows/integrate-rock.yaml)).

Both secrets must exist in this repo before running the workflow, otherwise they cannot be pushed downstream.

To add a new secret to the sync, add it both to the `secrets` list (as a regex, e.g. `^GH_TOKEN$`) and to the step's `env` block.

Run the workflow via Actions->Sync Github credentials to repos->Run workflow. Leave `DRY_RUN=true` to preview the changes, set it to `false` to actually push the secrets.

# sync_gpg_secrets.yaml

This workflow syncs `GPG_PASSPHRASE` and `GPG_PRIVATE_KEY`, used to sign commits and tags, to all repos listed in `sync_gpg_secrets.yaml`. It works the same way as `sync_github_token.yaml` described above.
