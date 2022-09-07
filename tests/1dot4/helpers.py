async def get_ingress_ip_1dot4(ops_test):
    status = await ops_test.model.get_status()
    public_url = (
        f"http://{status['applications']['istio-ingressgateway']['public-address']}.nip.io"
    )
    return public_url
