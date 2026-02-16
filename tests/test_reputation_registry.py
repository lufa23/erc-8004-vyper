"""Tests for ReputationRegistry"""

from eth_utils import keccak
from eth_abi import decode


# -- Helpers ----------------------------------------------------------------


NEW_FEEDBACK_SIG = keccak(
    text="NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)"
)


def _log_name(log):
    """Return the event name for both decoded and raw log entries."""
    name = type(log).__name__
    if name != "RawLogEntry":
        return name
    sig_int = int.from_bytes(NEW_FEEDBACK_SIG, "big")
    if len(log.topics) >= 1 and log.topics[0] == sig_int:
        return "NewFeedback"
    return "Unknown"


def _get_logs(contract):
    """Get logs with NewFeedback surviving the indexed-string decode issue."""
    return contract.get_logs(strict=False)


def _filter_logs(contract, event_name):
    """Return only logs matching event_name."""
    return [l for l in _get_logs(contract) if _log_name(l) == event_name]


# -- Tests ------------------------------------------------------------------


def test_get_identity_registry(reputation_registry, identity_registry):
    """getIdentityRegistry returns the address passed to __init__."""
    assert reputation_registry.getIdentityRegistry() == identity_registry.address


def test_give_feedback_basic(reputation_registry, identity_registry, deployer):
    """giveFeedback stores feedback and emits NewFeedback event."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 85, 0)

    logs = _get_logs(reputation_registry)
    # NewFeedback has indexed(String[TAG_MAX]) so may be raw
    fb_logs = [l for l in logs if _log_name(l) == "NewFeedback"]
    assert len(fb_logs) == 1


def test_give_feedback_tracks_client(reputation_registry, identity_registry):
    """giveFeedback adds msg.sender to the clients list (verified via event)."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 50, 0)

    # The NewFeedback event has clientAddress indexed — verify from raw log
    logs = _get_logs(reputation_registry)
    fb_logs = [l for l in logs if _log_name(l) == "NewFeedback"]
    assert len(fb_logs) == 1
    # topic[2] is the indexed clientAddress
    raw = fb_logs[0]
    client_topic = raw.topics[2]
    assert client_topic == int.from_bytes(bytes.fromhex(client[2:]), "big")


def test_give_feedback_increments_index(reputation_registry, identity_registry):
    """Two giveFeedback calls produce feedbackIndex 1 and 2."""
    import boa

    identity_registry.register()

    types = ["uint64", "int128", "uint8", "string", "string", "string", "string", "bytes32"]

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 10, 0)
    logs1 = [l for l in _get_logs(reputation_registry) if _log_name(l) == "NewFeedback"]
    assert len(logs1) == 1
    d1 = decode(types, logs1[0].data)
    assert d1[0] == 1  # feedbackIndex

    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 20, 0)
    logs2 = [l for l in _get_logs(reputation_registry) if _log_name(l) == "NewFeedback"]
    assert len(logs2) == 1
    d2 = decode(types, logs2[0].data)
    assert d2[0] == 2  # feedbackIndex


def test_give_feedback_nonexistent_agent(reputation_registry):
    """giveFeedback reverts for a non-existent agent."""
    import boa

    with boa.reverts():
        reputation_registry.giveFeedback(999, 50, 0)


def test_give_feedback_with_optional_params(reputation_registry, identity_registry):
    """giveFeedback with all optional params filled emits correct data."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(
            1,
            100,
            2,
            "quality",
            "speed",
            "https://api.example.com/v1",
            "https://feedback.example.com/1.json",
            b"\xab" * 32,
        )

    logs = _get_logs(reputation_registry)
    fb_logs = [l for l in logs if _log_name(l) == "NewFeedback"]
    assert len(fb_logs) == 1

    types = ["uint64", "int128", "uint8", "string", "string", "string", "string", "bytes32"]
    d = decode(types, fb_logs[0].data)
    assert d[0] == 1       # feedbackIndex
    assert d[1] == 100     # value
    assert d[2] == 2       # valueDecimals
    assert d[3] == "quality"  # tag1
    assert d[4] == "speed"    # tag2
    assert d[5] == "https://api.example.com/v1"        # endpoint
    assert d[6] == "https://feedback.example.com/1.json"  # feedbackURI
    assert d[7] == b"\xab" * 32  # feedbackHash


def test_revoke_feedback(reputation_registry, identity_registry):
    """revokeFeedback sets isRevoked and emits FeedbackRevoked."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 75, 0)
        reputation_registry.revokeFeedback(1, 1)

    logs = _get_logs(reputation_registry)
    revoked = [l for l in logs if _log_name(l) == "FeedbackRevoked"]
    assert len(revoked) == 1
    assert revoked[0].agentId == 1
    assert revoked[0].clientAddress == client
    assert revoked[0].feedbackIndex == 1


def test_revoke_feedback_wrong_client(reputation_registry, identity_registry):
    """revokeFeedback reverts when called by a different address."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 75, 0)

    other = boa.env.generate_address()
    with boa.env.prank(other):
        with boa.reverts("ReputationRegistry: feedback does not exist"):
            reputation_registry.revokeFeedback(1, 1)


def test_revoke_feedback_already_revoked(reputation_registry, identity_registry):
    """Double revoke reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 75, 0)
        reputation_registry.revokeFeedback(1, 1)
        with boa.reverts("ReputationRegistry: already revoked"):
            reputation_registry.revokeFeedback(1, 1)


def test_revoke_feedback_nonexistent(reputation_registry, identity_registry):
    """Revoking a non-existent feedback index reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        with boa.reverts("ReputationRegistry: feedback does not exist"):
            reputation_registry.revokeFeedback(1, 5)


# -- Task 2.3: appendResponse and getResponseCount -------------------------


def test_append_response_basic(reputation_registry, identity_registry, deployer):
    """appendResponse from agent owner emits event and increments count."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 80, 0)

    # Agent owner responds
    reputation_registry.appendResponse(1, client, 1, "https://response.io/1", b"\xcc" * 32)

    logs = _get_logs(reputation_registry)
    resp_logs = [l for l in logs if _log_name(l) == "ResponseAppended"]
    assert len(resp_logs) == 1
    assert resp_logs[0].agentId == 1
    assert resp_logs[0].clientAddress == client
    assert resp_logs[0].feedbackIndex == 1
    assert resp_logs[0].responder == deployer
    assert resp_logs[0].responseURI == "https://response.io/1"
    assert resp_logs[0].responseHash == b"\xcc" * 32

    assert reputation_registry.getResponseCount(1, client, 1) == 1


def test_append_response_anyone(reputation_registry, identity_registry):
    """A third party (not agent owner) can also respond."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 50, 0)

    third_party = boa.env.generate_address()
    with boa.env.prank(third_party):
        reputation_registry.appendResponse(1, client, 1)

    assert reputation_registry.getResponseCount(1, client, 1) == 1


def test_append_response_no_double(reputation_registry, identity_registry):
    """Same responder tries twice, second reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 50, 0)

    responder = boa.env.generate_address()
    with boa.env.prank(responder):
        reputation_registry.appendResponse(1, client, 1)
        with boa.reverts("ReputationRegistry: already responded"):
            reputation_registry.appendResponse(1, client, 1)


def test_append_response_nonexistent_feedback(reputation_registry, identity_registry):
    """appendResponse reverts for a non-existent feedback entry."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.reverts("ReputationRegistry: feedback does not exist"):
        reputation_registry.appendResponse(1, client, 5)


def test_append_response_revoked_feedback(reputation_registry, identity_registry):
    """appendResponse reverts if feedback was revoked."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 60, 0)
        reputation_registry.revokeFeedback(1, 1)

    with boa.reverts("ReputationRegistry: feedback is revoked"):
        reputation_registry.appendResponse(1, client, 1)


def test_append_response_multiple_responders(reputation_registry, identity_registry):
    """Two different addresses respond, count = 2."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 70, 0)

    r1 = boa.env.generate_address()
    r2 = boa.env.generate_address()
    with boa.env.prank(r1):
        reputation_registry.appendResponse(1, client, 1)
    with boa.env.prank(r2):
        reputation_registry.appendResponse(1, client, 1)

    assert reputation_registry.getResponseCount(1, client, 1) == 2


def test_get_response_count_default(reputation_registry, identity_registry):
    """getResponseCount returns 0 for unset entries."""
    import boa

    client = boa.env.generate_address()
    assert reputation_registry.getResponseCount(1, client, 1) == 0


# -- Task 2.4: Read & query functions --------------------------------------


def test_read_feedback(reputation_registry, identity_registry):
    """readFeedback returns all stored fields."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 85, 2, "quality", "speed")

    value, decimals, tag1, tag2, revoked = reputation_registry.readFeedback(1, client, 1)
    assert value == 85
    assert decimals == 2
    assert tag1 == "quality"
    assert tag2 == "speed"
    assert revoked is False


def test_read_feedback_revoked(reputation_registry, identity_registry):
    """readFeedback shows isRevoked=True after revocation."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 50, 0)
        reputation_registry.revokeFeedback(1, 1)

    _, _, _, _, revoked = reputation_registry.readFeedback(1, client, 1)
    assert revoked is True


def test_read_all_feedback_no_filter(reputation_registry, identity_registry):
    """readAllFeedback with no filters returns all feedback from all clients."""
    import boa

    identity_registry.register()

    c1 = boa.env.generate_address()
    c2 = boa.env.generate_address()
    with boa.env.prank(c1):
        reputation_registry.giveFeedback(1, 10, 0, "tag_a")
        reputation_registry.giveFeedback(1, 20, 0, "tag_b")
    with boa.env.prank(c2):
        reputation_registry.giveFeedback(1, 30, 0, "tag_c")

    results = reputation_registry.readAllFeedback(1)
    assert len(results) == 3

    # Results: c1 index 1, c1 index 2, c2 index 1
    assert results[0][0] == 1  # agentId
    assert results[0][1] == c1  # clientAddress
    assert results[0][2] == 1  # feedbackIndex
    assert results[0][3] == 10  # value

    assert results[1][1] == c1
    assert results[1][2] == 2
    assert results[1][3] == 20

    assert results[2][1] == c2
    assert results[2][2] == 1
    assert results[2][3] == 30


def test_read_all_feedback_client_filter(reputation_registry, identity_registry):
    """readAllFeedback filtered by specific client returns only that client's feedback."""
    import boa

    identity_registry.register()

    c1 = boa.env.generate_address()
    c2 = boa.env.generate_address()
    with boa.env.prank(c1):
        reputation_registry.giveFeedback(1, 10, 0)
    with boa.env.prank(c2):
        reputation_registry.giveFeedback(1, 20, 0)

    results = reputation_registry.readAllFeedback(1, [c2])
    assert len(results) == 1
    assert results[0][1] == c2
    assert results[0][3] == 20


def test_read_all_feedback_tag_filter(reputation_registry, identity_registry):
    """readAllFeedback filtered by tag returns matching entries."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 10, 0, "quality", "")
        reputation_registry.giveFeedback(1, 20, 0, "speed", "")
        reputation_registry.giveFeedback(1, 30, 0, "", "quality")  # tag2 match

    # Filter for "quality" — should match index 1 (tag1) and index 3 (tag2)
    results = reputation_registry.readAllFeedback(1, [], ["quality"])
    assert len(results) == 2
    assert results[0][2] == 1  # feedbackIndex
    assert results[0][3] == 10
    assert results[1][2] == 3
    assert results[1][3] == 30


def test_get_summary_basic(reputation_registry, identity_registry):
    """getSummary with 3 feedbacks: correct sum and counts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 10, 0)
        reputation_registry.giveFeedback(1, 20, 0)
        reputation_registry.giveFeedback(1, 30, 0)

    total, decimals, active, revoked = reputation_registry.getSummary(1)
    assert total == 60
    assert decimals == 0
    assert active == 3
    assert revoked == 0


def test_get_summary_with_revoked(reputation_registry, identity_registry):
    """getSummary excludes revoked feedback from sum but counts it."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 10, 0)
        reputation_registry.giveFeedback(1, 20, 0)
        reputation_registry.giveFeedback(1, 30, 0)
        reputation_registry.revokeFeedback(1, 2)  # revoke the 20

    total, decimals, active, revoked = reputation_registry.getSummary(1)
    assert total == 40  # 10 + 30
    assert active == 2
    assert revoked == 1


def test_get_summary_decimal_normalization(reputation_registry, identity_registry):
    """getSummary normalises values to the maximum valueDecimals."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        # 100 with 0 decimals = 100.
        reputation_registry.giveFeedback(1, 100, 0)
        # 250 with 2 decimals = 2.50
        reputation_registry.giveFeedback(1, 250, 2)

    total, decimals, active, revoked = reputation_registry.getSummary(1)
    # maxDecimals = 2
    # 100 normalised to 2 decimals: 100 * 10^2 = 10000
    # 250 already at 2 decimals: 250
    # total = 10250
    assert decimals == 2
    assert total == 10250
    assert active == 2
    assert revoked == 0


def test_get_clients(reputation_registry, identity_registry):
    """getClients returns unique client addresses."""
    import boa

    identity_registry.register()

    c1 = boa.env.generate_address()
    c2 = boa.env.generate_address()

    with boa.env.prank(c1):
        reputation_registry.giveFeedback(1, 10, 0)
        reputation_registry.giveFeedback(1, 20, 0)  # same client, no duplicate
    with boa.env.prank(c2):
        reputation_registry.giveFeedback(1, 30, 0)

    clients = reputation_registry.getClients(1)
    assert len(clients) == 2
    assert clients[0] == c1
    assert clients[1] == c2


def test_get_last_index(reputation_registry, identity_registry):
    """getLastIndex returns the correct index after multiple feedbacks."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    assert reputation_registry.getLastIndex(1, client) == 0

    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 10, 0)
    assert reputation_registry.getLastIndex(1, client) == 1

    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 20, 0)
    assert reputation_registry.getLastIndex(1, client) == 2


# -- Phase A.2: getVersion ----------------------------------------------------


def test_get_version(reputation_registry):
    """getVersion returns '1.0.0'."""
    assert reputation_registry.getVersion() == "1.0.0"


# -- Phase A.3: giveFeedback validation checks --------------------------------


def test_give_feedback_decimals_18_ok(reputation_registry, identity_registry):
    """giveFeedback with valueDecimals=18 (max) succeeds."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 1, 18)


def test_give_feedback_decimals_19_reverts(reputation_registry, identity_registry):
    """giveFeedback with valueDecimals=19 reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        with boa.reverts("ReputationRegistry: too many decimals"):
            reputation_registry.giveFeedback(1, 1, 19)


def test_give_feedback_value_at_positive_boundary(reputation_registry, identity_registry):
    """giveFeedback with value = +1e38 succeeds."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, 100000000000000000000000000000000000000, 0)


def test_give_feedback_value_at_negative_boundary(reputation_registry, identity_registry):
    """giveFeedback with value = -1e38 succeeds."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        reputation_registry.giveFeedback(1, -100000000000000000000000000000000000000, 0)


def test_give_feedback_value_over_positive_boundary(reputation_registry, identity_registry):
    """giveFeedback with value = +1e38 + 1 reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        with boa.reverts("ReputationRegistry: value out of range"):
            reputation_registry.giveFeedback(1, 100000000000000000000000000000000000001, 0)


def test_give_feedback_value_under_negative_boundary(reputation_registry, identity_registry):
    """giveFeedback with value = -1e38 - 1 reverts."""
    import boa

    identity_registry.register()

    client = boa.env.generate_address()
    with boa.env.prank(client):
        with boa.reverts("ReputationRegistry: value out of range"):
            reputation_registry.giveFeedback(1, -100000000000000000000000000000000000001, 0)


# -- Phase A.4: Self-feedback prevention --------------------------------------


def test_give_feedback_self_owner_reverts(reputation_registry, identity_registry, deployer):
    """giveFeedback reverts when caller is the agent owner."""
    import boa

    identity_registry.register()

    with boa.reverts("ReputationRegistry: self-feedback not allowed"):
        reputation_registry.giveFeedback(1, 50, 0)


def test_give_feedback_self_approved_reverts(reputation_registry, identity_registry, deployer):
    """giveFeedback reverts when caller is the approved address for the agent."""
    import boa

    identity_registry.register()

    approved = boa.env.generate_address()
    identity_registry.approve(approved, 1)

    with boa.env.prank(approved):
        with boa.reverts("ReputationRegistry: self-feedback not allowed"):
            reputation_registry.giveFeedback(1, 50, 0)


def test_give_feedback_self_operator_reverts(reputation_registry, identity_registry, deployer):
    """giveFeedback reverts when caller is an approved-for-all operator."""
    import boa

    identity_registry.register()

    operator = boa.env.generate_address()
    identity_registry.setApprovalForAll(operator, True)

    with boa.env.prank(operator):
        with boa.reverts("ReputationRegistry: self-feedback not allowed"):
            reputation_registry.giveFeedback(1, 50, 0)
