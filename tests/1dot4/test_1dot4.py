import shlex
import time

import pytest
from helpers import get_ingress_ip, kubeflow_login
from kfp import Client
from lightkube.models.rbac_v1 import PolicyRule
from lightkube.resources.rbac_authorization_v1 import Role
from pipelines.cowsay import cowsay_pipeline
from pipelines.jupyter import jupyter_pipeline
from pipelines.katib import katib_pipeline
from pipelines.mnist import mnist_pipeline
from pipelines.object_detection import object_detection_pipeline
from pytest_operator.plugin import OpsTest

from tests.helpers import get_pipeline_params

USERNAME = "admin"
PASSWORD = "secret"


@pytest.mark.abort_on_fail
@pytest.mark.deploy
async def test_deploy_1dot4(ops_test: OpsTest, lightkube_client, deploy_cmd):
    print(f"Deploying bundle to {ops_test.model_full_name} using cmd '{deploy_cmd}'")
    rc, stdout, stderr = await ops_test.run(*shlex.split(deploy_cmd))

    print("Waiting for istio-ingressgateway")
    await ops_test.model.wait_for_idle(
        ["istio-ingressgateway"],
        status="waiting",
        timeout=1800,
    )

    print("Patch role for istio-gateway")
    async with ops_test.fast_forward(fast_interval="15s"):
        istio_gateway_role_name = "istio-ingressgateway-operator"
        new_policy_rule = PolicyRule(verbs=["*"], apiGroups=["*"], resources=["*"])
        this_role = lightkube_client.get(Role, istio_gateway_role_name)
        this_role.rules.append(new_policy_rule)

        lightkube_client.patch(Role, istio_gateway_role_name, this_role)
        time.sleep(300)

    print("Waiting for bundle to be ready")
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=False,
        timeout=5000,
    )

    url = await get_ingress_ip(ops_test)

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


@pytest.mark.parametrize(
    "name, fn",
    [
        #("cowsay", cowsay_pipeline),
        #("jupyter", jupyter_pipeline),
        #("katib", katib_pipeline),
        #("object_detection", object_detection_pipeline),
        ("mnist", mnist_pipeline),
    ],
)
async def test_mnist_pipeline(ops_test: OpsTest, name, fn):
    url = await get_ingress_ip(ops_test)
    cookies = (
        f"authservice_session={kubeflow_login(host=url, username=USERNAME, password=PASSWORD)}"
    )
    pipeline_url = f"{url}/pipeline"
    client = Client(host=pipeline_url, namespace=USERNAME, cookies=cookies)
    run = client.create_run_from_pipeline_func(
        fn, arguments=get_pipeline_params(mnist_pipeline), namespace=USERNAME
    )
    completed = client.wait_for_run_completion(run.run_id, timeout=3600)
    status = completed.to_dict()["run"]["status"]
    assert status == "Succeeded", f"Pipeline {name} status is {status}"
