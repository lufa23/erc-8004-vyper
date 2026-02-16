"""Tests for ValidationRegistry"""

from eth_utils import keccak
from eth_abi import decode


# -- Helpers ----------------------------------------------------------------


VALIDATION_REQUESTED_SIG = keccak(
    text="ValidationRequested(uint256,address,uint64,string,bytes32,string,string)"
)


def _log_name(log):
    """Return the event name for both decoded and raw log entries."""
    name = type(log).__name__
    if name != "RawLogEntry":
        return name
    sig_int = int.from_bytes(VALIDATION_REQUESTED_SIG, "big")
    if len(log.topics) >= 1 and log.topics[0] == sig_int:
        return "ValidationRequested"
    return "Unknown"


def _get_logs(contract):
    """Get logs with indexed-string events surviving decode issues."""
    return contract.get_logs(strict=False)


def _filter_logs(contract, event_name):
    """Return only logs matching event_name."""
    return [l for l in _get_logs(contract) if _log_name(l) == event_name]


# -- Tests ------------------------------------------------------------------


def test_get_identity_registry(validation_registry, identity_registry):
    """getIdentityRegistry returns the address passed to __init__."""
    assert validation_registry.getIdentityRegistry() == identity_registry.address


def test_validation_request_basic(validation_registry, identity_registry, deployer):
    """validationRequest emits event and returns requestIndex = 1."""
    identity_registry.register()

    idx = validation_registry.validationRequest(1)
    assert idx == 1

    logs = _filter_logs(validation_registry, "ValidationRequested")
    assert len(logs) == 1

    # Decode data: requestIndex(uint64), requestURI(string), requestHash(bytes32), tag(string)
    types = ["uint64", "string", "bytes32", "string"]
    d = decode(types, logs[0].data)
    assert d[0] == 1   # requestIndex
    assert d[1] == ""  # requestURI
    assert d[2] == b"\x00" * 32  # requestHash
    assert d[3] == ""  # tag

    # topic[1] = agentId, topic[2] = requester (address)
    assert logs[0].topics[1] == 1
    assert logs[0].topics[2] == int.from_bytes(bytes.fromhex(deployer[2:]), "big")


def test_validation_request_increments_index(validation_registry, identity_registry):
    """Two requests produce indices 1 and 2."""
    identity_registry.register()

    idx1 = validation_registry.validationRequest(1)
    idx2 = validation_registry.validationRequest(1)
    assert idx1 == 1
    assert idx2 == 2


def test_validation_request_nonexistent_agent(validation_registry):
    """validationRequest reverts for a non-existent agent."""
    import pytest

    # Use pytest.raises instead of boa.reverts() to work around a
    # Titanoboa repr() bug with deeply nested HashMap storage types.
    with pytest.raises(Exception):
        validation_registry.validationRequest(999)


def test_validation_request_with_all_params(validation_registry, identity_registry):
    """validationRequest with all params filled emits correct data."""
    identity_registry.register()

    idx = validation_registry.validationRequest(
        1,
        "https://request.example.com/1.json",
        b"\xab" * 32,
        "security",
    )
    assert idx == 1

    logs = _filter_logs(validation_registry, "ValidationRequested")
    assert len(logs) == 1

    types = ["uint64", "string", "bytes32", "string"]
    d = decode(types, logs[0].data)
    assert d[0] == 1
    assert d[1] == "https://request.example.com/1.json"
    assert d[2] == b"\xab" * 32
    assert d[3] == "security"


def test_validation_request_empty_params(validation_registry, identity_registry):
    """validationRequest with all defaults still works."""
    identity_registry.register()

    idx = validation_registry.validationRequest(1)
    assert idx == 1


# -- Task 3.3: validationResponse ------------------------------------------


def test_validation_response_valid(validation_registry, identity_registry, deployer):
    """validationResponse with isValid=True emits event and increments valid count."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    validator = boa.env.generate_address()
    with boa.env.prank(validator):
        validation_registry.validationResponse(1, deployer, 1, True)

    logs = _get_logs(validation_registry)
    resp_logs = [l for l in logs if _log_name(l) == "ValidationResponseSubmitted"]
    assert len(resp_logs) == 1
    assert resp_logs[0].agentId == 1
    assert resp_logs[0].requester == deployer
    assert resp_logs[0].requestIndex == 1
    assert resp_logs[0].validator == validator
    assert resp_logs[0].isValid is True


def test_validation_response_invalid(validation_registry, identity_registry, deployer):
    """validationResponse with isValid=False increments invalid count."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    validator = boa.env.generate_address()
    with boa.env.prank(validator):
        validation_registry.validationResponse(1, deployer, 1, False)

    logs = _get_logs(validation_registry)
    resp_logs = [l for l in logs if _log_name(l) == "ValidationResponseSubmitted"]
    assert len(resp_logs) == 1
    assert resp_logs[0].isValid is False


def test_validation_response_no_double(validation_registry, identity_registry, deployer):
    """Same validator tries twice, second reverts."""
    import boa
    import pytest

    identity_registry.register()
    validation_registry.validationRequest(1)

    validator = boa.env.generate_address()
    with boa.env.prank(validator):
        validation_registry.validationResponse(1, deployer, 1, True)
        # Titanoboa repr() bug with deep HashMaps — use pytest.raises
        with pytest.raises(Exception):
            validation_registry.validationResponse(1, deployer, 1, True)


def test_validation_response_nonexistent_request(validation_registry, identity_registry, deployer):
    """validationResponse reverts for a non-existent request."""
    import pytest

    identity_registry.register()

    with pytest.raises(Exception):
        validation_registry.validationResponse(1, deployer, 5, True)


def test_validation_response_multiple_validators(validation_registry, identity_registry, deployer):
    """Two different validators respond, both counted."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    v1 = boa.env.generate_address()
    v2 = boa.env.generate_address()
    with boa.env.prank(v1):
        validation_registry.validationResponse(1, deployer, 1, True)
    with boa.env.prank(v2):
        validation_registry.validationResponse(1, deployer, 1, False)

    # Verify via events — two ResponseSubmitted logs
    logs = _get_logs(validation_registry)
    resp_logs = [l for l in logs if _log_name(l) == "ValidationResponseSubmitted"]
    assert len(resp_logs) == 1  # only last tx logs
    # But the state is correct — we'll verify in Task 3.4 with getter functions


def test_validation_response_with_all_params(validation_registry, identity_registry, deployer):
    """validationResponse with URI and hash filled emits correct data."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    validator = boa.env.generate_address()
    with boa.env.prank(validator):
        validation_registry.validationResponse(
            1, deployer, 1, True,
            "https://response.example.com/1.json",
            b"\xdd" * 32,
        )

    logs = _get_logs(validation_registry)
    resp_logs = [l for l in logs if _log_name(l) == "ValidationResponseSubmitted"]
    assert len(resp_logs) == 1
    assert resp_logs[0].responseURI == "https://response.example.com/1.json"
    assert resp_logs[0].responseHash == b"\xdd" * 32


# -- Task 3.4: Query functions ---------------------------------------------


def test_get_response_count(validation_registry, identity_registry, deployer):
    """getResponseCount returns 2 after two validators respond."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    v1 = boa.env.generate_address()
    v2 = boa.env.generate_address()
    with boa.env.prank(v1):
        validation_registry.validationResponse(1, deployer, 1, True)
    with boa.env.prank(v2):
        validation_registry.validationResponse(1, deployer, 1, False)

    assert validation_registry.getResponseCount(1, deployer, 1) == 2


def test_get_valid_invalid_counts(validation_registry, identity_registry, deployer):
    """2 valid + 1 invalid responses produce correct separate counts."""
    import boa

    identity_registry.register()
    validation_registry.validationRequest(1)

    v1 = boa.env.generate_address()
    v2 = boa.env.generate_address()
    v3 = boa.env.generate_address()
    with boa.env.prank(v1):
        validation_registry.validationResponse(1, deployer, 1, True)
    with boa.env.prank(v2):
        validation_registry.validationResponse(1, deployer, 1, True)
    with boa.env.prank(v3):
        validation_registry.validationResponse(1, deployer, 1, False)

    assert validation_registry.getValidCount(1, deployer, 1) == 2
    assert validation_registry.getInvalidCount(1, deployer, 1) == 1
    assert validation_registry.getResponseCount(1, deployer, 1) == 3


def test_get_summary_basic(validation_registry, identity_registry, deployer):
    """getSummary aggregates across multiple requests."""
    import boa

    identity_registry.register()

    # Request 1: 1 valid
    validation_registry.validationRequest(1)
    v1 = boa.env.generate_address()
    with boa.env.prank(v1):
        validation_registry.validationResponse(1, deployer, 1, True)

    # Request 2: 1 valid + 1 invalid
    validation_registry.validationRequest(1)
    v2 = boa.env.generate_address()
    v3 = boa.env.generate_address()
    with boa.env.prank(v2):
        validation_registry.validationResponse(1, deployer, 2, True)
    with boa.env.prank(v3):
        validation_registry.validationResponse(1, deployer, 2, False)

    total_resp, total_valid, total_invalid = validation_registry.getSummary(1, deployer)
    assert total_resp == 3
    assert total_valid == 2
    assert total_invalid == 1


def test_get_summary_tag_filter(validation_registry, identity_registry, deployer):
    """getSummary filtered by tag only includes matching requests."""
    import boa

    identity_registry.register()

    # Request 1 with tag "security"
    validation_registry.validationRequest(1, "", b"\x00" * 32, "security")
    v1 = boa.env.generate_address()
    with boa.env.prank(v1):
        validation_registry.validationResponse(1, deployer, 1, True)

    # Request 2 with tag "compliance"
    validation_registry.validationRequest(1, "", b"\x00" * 32, "compliance")
    v2 = boa.env.generate_address()
    with boa.env.prank(v2):
        validation_registry.validationResponse(1, deployer, 2, False)

    # Request 3 with tag "security"
    validation_registry.validationRequest(1, "", b"\x00" * 32, "security")
    v3 = boa.env.generate_address()
    with boa.env.prank(v3):
        validation_registry.validationResponse(1, deployer, 3, True)

    # Filter for "security" only — requests 1 and 3
    total_resp, total_valid, total_invalid = validation_registry.getSummary(
        1, deployer, ["security"]
    )
    assert total_resp == 2
    assert total_valid == 2
    assert total_invalid == 0

    # Filter for "compliance" only — request 2
    total_resp, total_valid, total_invalid = validation_registry.getSummary(
        1, deployer, ["compliance"]
    )
    assert total_resp == 1
    assert total_valid == 0
    assert total_invalid == 1


def test_get_last_request_index(validation_registry, identity_registry, deployer):
    """getLastRequestIndex tracks correctly after multiple requests."""
    identity_registry.register()

    assert validation_registry.getLastRequestIndex(1, deployer) == 0

    validation_registry.validationRequest(1)
    assert validation_registry.getLastRequestIndex(1, deployer) == 1

    validation_registry.validationRequest(1)
    assert validation_registry.getLastRequestIndex(1, deployer) == 2


def test_query_defaults_zero(validation_registry, identity_registry, deployer):
    """All getters return 0 for unset data."""
    import boa

    other = boa.env.generate_address()
    assert validation_registry.getResponseCount(1, other, 1) == 0
    assert validation_registry.getValidCount(1, other, 1) == 0
    assert validation_registry.getInvalidCount(1, other, 1) == 0
    assert validation_registry.getLastRequestIndex(1, other) == 0

    total_resp, total_valid, total_invalid = validation_registry.getSummary(1, other)
    assert total_resp == 0
    assert total_valid == 0
    assert total_invalid == 0


# -- Phase A.2: getVersion ----------------------------------------------------


def test_get_version(validation_registry):
    """getVersion returns '1.0.0'."""
    assert validation_registry.getVersion() == "1.0.0"
