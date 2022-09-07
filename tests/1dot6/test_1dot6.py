import shlex

import pytest
from kfp import Client
from pipelines.mnist import mnist_pipeline
from pytest_operator.plugin import OpsTest

from helpers import get_ingress_url
from tests.helpers import get_pipeline_params, kubeflow_login

USERNAME = "admin"
PASSWORD = "secret"


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_1dot6(ops_test: OpsTest, lightkube_client, deploy_cmd):
    print(f"Deploying bundle to {ops_test.model_full_name} using cmd '{deploy_cmd}'")
    rc, stdout, stderr = await ops_test.run(*shlex.split(deploy_cmd))

    print("Waiting for bundle to be ready")
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=True,
        timeout=3000,
    )
    url = get_ingress_url(lightkube_client, ops_test.model_name)

    print("Update Dex and OIDC configs")
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


async def test_mnist_pipeline(ops_test: OpsTest, lightkube_client):
    name = "mnist"
    url = get_ingress_url(lightkube_client, ops_test.model_name)
    cookies = (
        f"authservice_session={kubeflow_login(host=url, username=USERNAME, password=PASSWORD)}"
    )
    pipeline_url = f"{url}/pipeline"
    client = Client(host=pipeline_url, namespace=USERNAME, cookies=cookies)
    run = client.create_run_from_pipeline_func(
        mnist_pipeline, arguments=get_pipeline_params(mnist_pipeline), namespace=USERNAME
    )
    completed = client.wait_for_run_completion(run.run_id, timeout=3600)
    status = completed.to_dict()["run"]["status"]
    assert status == "Succeeded", f"Pipeline {name} status is {status}"
