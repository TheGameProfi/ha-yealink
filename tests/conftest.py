from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fixed_local_ip(request):
    """Tests run without network: pretend HA reaches the phone from 192.168.2.30."""
    if "real_ip" in request.keywords:
        yield
        return
    with patch("custom_components.yealink.provision.local_ip_towards", return_value="192.168.2.30"):
        yield
