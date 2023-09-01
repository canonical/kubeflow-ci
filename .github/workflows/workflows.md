
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
