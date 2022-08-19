import shlex
import time

import pytest
from helpers import get_ingress_ip_1dot4, get_ingress_url
from lightkube.models.rbac_v1 import PolicyRule
from lightkube.resources.core_v1 import Service
from lightkube.resources.rbac_authorization_v1 import Role
from pytest_operator.plugin import OpsTest

USERNAME = "admin"
PASSWORD = "foobar"


@pytest.mark.v1dot6
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_1dot6(ops_test, lightkube_client, deploy_cmd):
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


@pytest.mark.v1dot4
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_1dot4(ops_test, lightkube_client, deploy_cmd):
    print(f"Deploying bundle to {ops_test.model_full_name} using cmd '{deploy_cmd}'")
    rc, stdout, stderr = await ops_test.run(*shlex.split(deploy_cmd))

    print("Waiting for istio-ingressgateway")
    await ops_test.model.wait_for_idle(
        ["istio-ingressgateway"],
        status="waiting",
        timeout=1800,
    )

    await ops_test.model.set_config({"update-status-hook-interval": "15s"})
    istio_gateway_role_name = "istio-ingressgateway-operator"

    print("Patch role for istio-gateway")
    new_policy_rule = PolicyRule(verbs=["*"], apiGroups=["*"], resources=["*"])
    this_role = lightkube_client.get(Role, istio_gateway_role_name)
    this_role.rules.append(new_policy_rule)
    lightkube_client.patch(Role, istio_gateway_role_name, this_role)

    time.sleep(50)
    await ops_test.model.set_config({"update-status-hook-interval": "5m"})

    print("Waiting for bundle to be ready")
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=True,
        timeout=3000,
    )

    url = await get_ingress_ip_1dot4(ops_test)

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
