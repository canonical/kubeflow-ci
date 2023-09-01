# request_missing_tracks

This script is for parsing a bundle file, identifying any tracks that are referenced but do not exist, and printing a formatted message suitable for requesting those missing tracks.  

Note that this script works on **tracks**, not channels.

## Example

Given this `bundle.yaml` file:
```yaml
bundle: kubernetes
name: kubeflow
applications:
  admission-webhook:
    charm: admission-webhook
    channel: latest/edge             # <--- Track for this channel exists
    scale: 1
  argo-controller:
    charm: argo-controller
    channel: NOT-A-REAL-CHANNEL/edge                # <--- Track for this channel does not exist
    scale: 1
```

We can execute `python ./request_missing_tracks.py bundle.yaml` to get the following output:

```
At least one track in the bundle found missing.  To create this track, submit the below request to: https://discourse.charmhub.io/c/charmhub-requests

Subject:
Request: Add tracks to Charms

Body:
Hello!  Can we please add the following tracks to the cited charms?  Thanks!

	Charm: Track

	argo-controller: NOT-A-REAL-CHANNEL
```

## Tests

`cd scripts/request_missing_tracks && pytest ./test_request_missing_tracks.py`
