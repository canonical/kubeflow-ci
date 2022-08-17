import pytest
import shlex
from pytest_operator.plugin import OpsTest
import lightkube
from lightkube.resources.core_v1 import Service

USERNAME = "admin"
PASSWORD = "foobar"


def get_ingress_ip(lightkube_client, model_name):
    gateway_svc = lightkube_client.get(
        Service, "istio-ingressgateway-workload", namespace=model_name
    )

    endpoint = gateway_svc.status.loadBalancer.ingress[0].ip
    return endpoint


@pytest.fixture(scope="session")
def lightkube_client():
    yield lightkube.Client()


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy(ops_test, request, lightkube_client):
    if ops_test.model_name != "kubeflow":
        raise ValueError("kfp must be deployed to namespace kubeflow")

    bundle_file = request.config.getoption("file", default=None)
    channel = request.config.getoption("channel", default=None)

    if (bundle_file is None and channel is None) or (bundle_file and channel):
        raise ValueError("One of --file or --channel is required")

    model = ops_test.model_full_name

    if bundle_file:
        # pytest automatically prune path to relative paths without `./`
        # juju deploys requires `./`
        cmd = f"juju deploy -m {model} --trust ./{bundle_file}"
    if channel:
        cmd = f"juju deploy kubeflow -m {model} --trust --channel {channel}"

    print(f"Deploying bundle to {model} using cmd '{cmd}'")
    rc, stdout, stderr = await ops_test.run(*shlex.split(cmd))
    if stderr:
        print(stderr)
        raise RuntimeError("failed to deploy")

    print("Waiting for bundle to be ready")
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=True,
        timeout=3000,
    )
    endpoint = get_ingress_ip(lightkube_client, ops_test.model_name)
    url = f"http://{endpoint}.nip.io"

    await ops_test.model.applications["dex-auth"].set_config(
        {"public-url": url, "static-username": USERNAME, "static-password": PASSWORD}
    )
    await ops_test.model.applications["oidc-gatekeeper"].set_config({"public-url": url})

    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=True,
        timeout=600,
    )
