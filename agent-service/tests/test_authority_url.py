import pytest

from lecturelens_agent.study.authority import EvidenceAuthority


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8084",
        "http://localhost:8084",
        "http://100.68.169.36:8084",
        "https://java.example.test",
    ],
)
def test_evidence_authority_accepts_local_tailscale_or_https(url):
    assert EvidenceAuthority(url, "test-secret").url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:8084",
        "http://192.168.1.5:8084",
        "http://8.8.8.8:8084",
        "http://100.68.169.36",
        "http://100.68.169.36:8084@attacker.example",
        "http://100.68.169.36:8084/other",
        "http://100.68.169.36:8084?next=other",
    ],
)
def test_evidence_authority_rejects_other_http_destinations(url):
    with pytest.raises(RuntimeError, match="Invalid AGENT_JAVA_BASE_URL"):
        EvidenceAuthority(url, "test-secret")
