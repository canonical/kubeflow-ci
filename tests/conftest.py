from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--file",
        help="Path to bundle file to use as the template for tests.  This must include all charms"
        "built by this bundle, where the locally built charms will replace those specified. "
        "This is useful for testing this bundle against different external dependencies. "
        "e.g. ./releases/1.6/kubeflow-bundle.yaml",
    )

    parser.addoption(
        "--channel",
        help="Kubeflow channels, e.g. latest/stable, 1.6/beta",
    )
