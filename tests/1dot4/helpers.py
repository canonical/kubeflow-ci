import logging
import os
from urllib.parse import parse_qs

import requests

from tests.helpers import validate_response_status_code


async def get_ingress_ip(ops_test):
    status = await ops_test.model.get_status()
    public_url = (
        f"http://{status['applications']['istio-ingressgateway']['public-address']}.nip.io"
    )
    return public_url


def kubeflow_login(host, username=None, password=None):
    """Completes the dex/oidc login flow, returning the authservice_session cookie."""
    host = host.rstrip("/")
    data = {
        "login": username or os.getenv("KUBEFLOW_USERNAME", None),
        "password": password or os.getenv("KUBEFLOW_PASSWORD", None),
    }

    if not data["login"] or not data["password"]:
        raise ValueError(
            "Missing login credentials - credentials must be passed or defined"
            " in KUBEFLOW_USERNAME/KUBEFLOW_PASSWORD environment variables."
        )

    # GET on host provides us a location header with the dex auth page
    # and state for this session
    response = requests.get(host, verify=False, allow_redirects=False)
    validate_response_status_code(response, [302], f"Failed to connect to host site '{host}'.")
    location = response.headers["location"]

    # Preserve only first portion of state if there are multiple, then rebuild
    # the dex_url
    state = parse_qs(location)["state"][0]
    location_prefix, _ = location.split("state=")
    location = location_prefix + f"state={state}"
    dex_url = location
    logging.debug(f"Redirected to dex_url of '{dex_url}'")

    # GET on the dex_url provides the dex auth login url we can use and a
    # request token
    response = requests.get(dex_url, verify=False, allow_redirects=False)
    validate_response_status_code(response, [302], f"Failed to connect to dex_url '{dex_url}'.")

    if response.status_code != 302:
        raise ValueError(
            f"Failed to connect to host site.  "
            f"Got response {response.status_code}, expected 302"
        )
    dex_login_partial_url = response.headers["location"]
    dex_login_url = f"{host}{dex_login_partial_url}"
    logging.debug(f"Got dex_login_url with request token of '{dex_login_url}")

    # Log in
    response = requests.post(dex_login_url, data=data, verify=False, allow_redirects=False)
    validate_response_status_code(
        response, [301, 303], f"Failed to log into dex - are your credentials correct?"
    )
    dex_approval_partial_url = response.headers["location"]
    dex_approval_url = f"{host}{dex_approval_partial_url}"
    logging.debug(f"Got dex_approval_url of '{dex_approval_url}")

    # GET and return the authservice_session cookie
    response = requests.get(dex_approval_url, verify=False, allow_redirects=False)
    validate_response_status_code(
        response, [301, 303], f"Failed to connect to dex_approval_url '{dex_approval_url}'."
    )
    authservice_partial_url = response.headers["location"]
    authservice_url = f"{host}{authservice_partial_url}"
    logging.debug(f"Got authservice_url of '{authservice_url}'")

    response = requests.get(authservice_url, verify=False, allow_redirects=False)
    validate_response_status_code(
        response, [301, 302], f"Failed to connect to authservice_url '{authservice_url}'."
    )

    return response.cookies["authservice_session"]
