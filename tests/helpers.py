def get_ingress_url(lightkube_client, model_name):
    gateway_svc = lightkube_client.get(
        Service, "istio-ingressgateway-workload", namespace=model_name
    )

    public_url = f"http://{gateway_svc.status.loadBalancer.ingress[0].ip}.nip.io"
    return public_url


async def get_ingress_ip_1dot4(ops_test):
    status = await ops_test.model.get_status()
    public_url = (
        f"http://{status['applications']['istio-ingressgateway']['public-address']}.nip.io"
    )
    return public_url
