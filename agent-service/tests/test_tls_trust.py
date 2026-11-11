"""The active HTTP client must not trust the withdrawn emSign ECC root."""

import ssl
from pathlib import Path
from unittest.mock import patch

import certifi
import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID


def test_active_ca_bundle_excludes_compromised_chain_root():
    roots = x509.load_pem_x509_certificates(Path(certifi.where()).read_bytes())
    names = {
        attribute.value
        for root in roots
        for attribute in root.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    }
    assert "emSign ECC Root CA - G3" not in names
    assert "ISRG Root X1" in names


def test_httpx_default_verification_uses_active_bundle_with_hostname_checks():
    with patch("ssl.create_default_context", wraps=ssl.create_default_context) as create:
        context = httpx.create_ssl_context(trust_env=False)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        create.assert_called_once_with(cafile=certifi.where())
