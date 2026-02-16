# pragma version ~=0.4.3
"""
@title ERC-8004 Reputation Registry
@custom:contract-name ReputationRegistry
@license UNLICENSED
@notice On-chain feedback and reputation system for ERC-8004 agents.
        Tracks feedback entries per (agentId, clientAddress) pair with
        tag-based filtering, revocation, and response tracking.
        References the Identity Registry for agent existence and
        ownership checks via staticcall.
"""


from interfaces import IIdentityRegistry


# @dev Max-size constants (UPPER_SNAKE_CASE, no leading underscore).
TAG_MAX: constant(uint256) = 64
LINK_MAX: constant(uint256) = 512
ARRAY_RETURN_MAX: constant(uint256) = 1024
FILTER_ARRAY_MAX: constant(uint256) = 128


struct FeedbackEntry:
    value: int128
    valueDecimals: uint8
    tag1: String[TAG_MAX]
    tag2: String[TAG_MAX]
    isRevoked: bool


struct FeedbackResult:
    agentId: uint256
    clientAddress: address
    feedbackIndex: uint64
    value: int128
    valueDecimals: uint8
    tag1: String[TAG_MAX]
    tag2: String[TAG_MAX]
    isRevoked: bool


event NewFeedback:
    agentId: indexed(uint256)
    clientAddress: indexed(address)
    feedbackIndex: uint64
    value: int128
    valueDecimals: uint8
    indexedTag1: indexed(String[TAG_MAX])
    tag1: String[TAG_MAX]
    tag2: String[TAG_MAX]
    endpoint: String[LINK_MAX]
    feedbackURI: String[LINK_MAX]
    feedbackHash: bytes32


event FeedbackRevoked:
    agentId: indexed(uint256)
    clientAddress: indexed(address)
    feedbackIndex: indexed(uint64)


event ResponseAppended:
    agentId: indexed(uint256)
    clientAddress: indexed(address)
    feedbackIndex: uint64
    responder: indexed(address)
    responseURI: String[LINK_MAX]
    responseHash: bytes32


# @dev Address of the IdentityRegistry contract, set once at deploy time.
_IDENTITY_REGISTRY: immutable(IIdentityRegistry)


# @dev Feedback storage: agentId → clientAddress → feedbackIndex → FeedbackEntry.
_feedback: HashMap[uint256, HashMap[address, HashMap[uint64, FeedbackEntry]]]


# @dev Last feedback index per (agentId, clientAddress) pair. 1-indexed.
_last_index: HashMap[uint256, HashMap[address, uint64]]


# @dev List of unique client addresses per agentId.
_clients: HashMap[uint256, DynArray[address, ARRAY_RETURN_MAX]]


# @dev Quick lookup: whether an address is already a client for an agentId.
_is_client: HashMap[uint256, HashMap[address, bool]]


# @dev Response count per feedback entry: agentId → clientAddress → feedbackIndex → count.
_response_count: HashMap[uint256, HashMap[address, HashMap[uint64, uint64]]]


# @dev Whether a responder has already responded to a feedback entry.
_has_responded: HashMap[uint256, HashMap[address, HashMap[uint64, HashMap[address, bool]]]]


@deploy
@payable
def __init__(identityRegistry_: address):
    """
    @dev To omit the opcodes for checking the `msg.value`
         in the creation-time EVM bytecode, the constructor
         is declared as `payable`.
    @notice Initialises the Reputation Registry with a reference
            to the Identity Registry contract.
    @param identityRegistry_ The address of the Identity Registry.
    """
    _IDENTITY_REGISTRY = IIdentityRegistry(identityRegistry_)


@external
@view
def getIdentityRegistry() -> address:
    """
    @dev Returns the address of the Identity Registry contract.
    @return address The Identity Registry address.
    """
    return _IDENTITY_REGISTRY.address


@external
def giveFeedback(
    agentId: uint256,
    feedbackValue: int128,
    valueDecimals: uint8,
    tag1: String[TAG_MAX] = "",
    tag2: String[TAG_MAX] = "",
    endpoint: String[LINK_MAX] = "",
    feedbackURI: String[LINK_MAX] = "",
    feedbackHash: bytes32 = empty(bytes32),
):
    """
    @dev Submits feedback for `agentId`. The agent must exist in the
         Identity Registry. Feedback is indexed per (agentId, msg.sender)
         pair with 1-based indices.
    @notice tag1, tag2, endpoint, feedbackURI, and feedbackHash are
            all optional (pass empty string / zero bytes to omit).
            The parameter is named `feedbackValue` because `value` is
            reserved in Vyper (msg.value). The ABI selector is
            unaffected since it depends only on types.
    @param agentId The agent to give feedback for.
    @param feedbackValue The feedback score.
    @param valueDecimals The number of decimals in `feedbackValue` (0–18).
    @param tag1 Primary tag for categorisation (optional).
    @param tag2 Secondary tag for categorisation (optional).
    @param endpoint The endpoint URI related to the feedback (optional).
    @param feedbackURI URI pointing to off-chain feedback content (optional).
    @param feedbackHash keccak256 of content at feedbackURI (optional).
    """
    # Verify agent exists (reverts if token does not exist).
    owner: address = staticcall _IDENTITY_REGISTRY.ownerOf(agentId)

    assert valueDecimals <= 18, "ReputationRegistry: too many decimals"
    assert feedbackValue >= -100000000000000000000000000000000000000 and feedbackValue <= 100000000000000000000000000000000000000, "ReputationRegistry: value out of range"

    # Self-feedback prevention: caller must not be the owner, approved address,
    # or an approved-for-all operator for the agent.
    assert msg.sender != owner, "ReputationRegistry: self-feedback not allowed"
    assert msg.sender != staticcall _IDENTITY_REGISTRY.getApproved(agentId), "ReputationRegistry: self-feedback not allowed"
    assert not staticcall _IDENTITY_REGISTRY.isApprovedForAll(owner, msg.sender), "ReputationRegistry: self-feedback not allowed"

    idx: uint64 = self._last_index[agentId][msg.sender] + 1
    self._last_index[agentId][msg.sender] = idx

    self._feedback[agentId][msg.sender][idx] = FeedbackEntry(
        value=feedbackValue,
        valueDecimals=valueDecimals,
        tag1=tag1,
        tag2=tag2,
        isRevoked=False,
    )

    if not self._is_client[agentId][msg.sender]:
        self._is_client[agentId][msg.sender] = True
        self._clients[agentId].append(msg.sender)

    log NewFeedback(
        agentId=agentId,
        clientAddress=msg.sender,
        feedbackIndex=idx,
        value=feedbackValue,
        valueDecimals=valueDecimals,
        indexedTag1=tag1,
        tag1=tag1,
        tag2=tag2,
        endpoint=endpoint,
        feedbackURI=feedbackURI,
        feedbackHash=feedbackHash,
    )


@external
def revokeFeedback(agentId: uint256, feedbackIndex: uint64):
    """
    @dev Revokes a previously submitted feedback entry. Only the
         original client (msg.sender) who submitted the feedback
         can revoke it.
    @param agentId The agent the feedback was given for.
    @param feedbackIndex The 1-based index of the feedback entry.
    """
    assert feedbackIndex > 0 and feedbackIndex <= self._last_index[agentId][msg.sender], "ReputationRegistry: feedback does not exist"
    assert not self._feedback[agentId][msg.sender][feedbackIndex].isRevoked, "ReputationRegistry: already revoked"

    self._feedback[agentId][msg.sender][feedbackIndex].isRevoked = True

    log FeedbackRevoked(
        agentId=agentId,
        clientAddress=msg.sender,
        feedbackIndex=feedbackIndex,
    )


@external
def appendResponse(
    agentId: uint256,
    clientAddress: address,
    feedbackIndex: uint64,
    responseURI: String[LINK_MAX] = "",
    responseHash: bytes32 = empty(bytes32),
    tag: String[TAG_MAX] = "",
):
    """
    @dev Appends a response to a feedback entry. Anyone can respond,
         but each address may only respond once per feedback entry.
    @notice The `tag` parameter is emitted in the event for off-chain
            indexing but is not stored on-chain.
    @param agentId The agent the feedback was given for.
    @param clientAddress The address that submitted the feedback.
    @param feedbackIndex The 1-based index of the feedback entry.
    @param responseURI URI pointing to off-chain response content (optional).
    @param responseHash keccak256 of content at responseURI (optional).
    @param tag Tag for categorisation, event-only (optional).
    """
    assert feedbackIndex > 0 and feedbackIndex <= self._last_index[agentId][clientAddress], "ReputationRegistry: feedback does not exist"
    assert not self._feedback[agentId][clientAddress][feedbackIndex].isRevoked, "ReputationRegistry: feedback is revoked"
    assert not self._has_responded[agentId][clientAddress][feedbackIndex][msg.sender], "ReputationRegistry: already responded"

    self._has_responded[agentId][clientAddress][feedbackIndex][msg.sender] = True
    self._response_count[agentId][clientAddress][feedbackIndex] += 1

    log ResponseAppended(
        agentId=agentId,
        clientAddress=clientAddress,
        feedbackIndex=feedbackIndex,
        responder=msg.sender,
        responseURI=responseURI,
        responseHash=responseHash,
    )


@external
@view
def getResponseCount(agentId: uint256, clientAddress: address, feedbackIndex: uint64) -> uint64:
    """
    @dev Returns the number of responses for a feedback entry.
    @param agentId The agent the feedback was given for.
    @param clientAddress The address that submitted the feedback.
    @param feedbackIndex The 1-based index of the feedback entry.
    @return uint64 The response count.
    """
    return self._response_count[agentId][clientAddress][feedbackIndex]


@internal
@pure
def _in_tags(tag: String[TAG_MAX], tags: DynArray[String[TAG_MAX], FILTER_ARRAY_MAX]) -> bool:
    """
    @dev Returns True if `tag` is found in `tags`.
    """
    for t: String[TAG_MAX] in tags:
        if t == tag:
            return True
    return False


@external
@view
def readFeedback(agentId: uint256, clientAddress: address, feedbackIndex: uint64) -> (int128, uint8, String[TAG_MAX], String[TAG_MAX], bool):
    """
    @dev Returns the stored fields of a single feedback entry.
    @param agentId The agent the feedback was given for.
    @param clientAddress The address that submitted the feedback.
    @param feedbackIndex The 1-based index of the feedback entry.
    @return (value, valueDecimals, tag1, tag2, isRevoked).
    """
    entry: FeedbackEntry = self._feedback[agentId][clientAddress][feedbackIndex]
    return (entry.value, entry.valueDecimals, entry.tag1, entry.tag2, entry.isRevoked)


@external
@view
def readAllFeedback(
    agentId: uint256,
    clients: DynArray[address, FILTER_ARRAY_MAX] = [],
    tags: DynArray[String[TAG_MAX], FILTER_ARRAY_MAX] = [],
) -> DynArray[FeedbackResult, ARRAY_RETURN_MAX]:
    """
    @dev Returns all feedback entries for `agentId`, optionally filtered
         by client addresses and/or tags.
    @param agentId The agent to read feedback for.
    @param clients Client addresses to filter by (empty = all clients).
    @param tags Tags to filter by (empty = no tag filter). An entry
           matches if its tag1 OR tag2 is in `tags`.
    @return DynArray of FeedbackResult structs.
    """
    result: DynArray[FeedbackResult, ARRAY_RETURN_MAX] = []

    client_list: DynArray[address, ARRAY_RETURN_MAX] = []
    if len(clients) == 0:
        client_list = self._clients[agentId]
    else:
        for c: address in clients:
            client_list.append(c)

    has_tag_filter: bool = len(tags) > 0

    for client: address in client_list:
        last: uint256 = convert(self._last_index[agentId][client], uint256)
        for i: uint256 in range(last, bound=ARRAY_RETURN_MAX):
            idx: uint64 = convert(i + 1, uint64)
            entry: FeedbackEntry = self._feedback[agentId][client][idx]

            if has_tag_filter:
                if not self._in_tags(entry.tag1, tags) and not self._in_tags(entry.tag2, tags):
                    continue

            result.append(FeedbackResult(
                agentId=agentId,
                clientAddress=client,
                feedbackIndex=idx,
                value=entry.value,
                valueDecimals=entry.valueDecimals,
                tag1=entry.tag1,
                tag2=entry.tag2,
                isRevoked=entry.isRevoked,
            ))

    return result


@external
@view
def getSummary(
    agentId: uint256,
    clients: DynArray[address, FILTER_ARRAY_MAX] = [],
    tags: DynArray[String[TAG_MAX], FILTER_ARRAY_MAX] = [],
) -> (int128, uint8, uint64, uint64):
    """
    @dev Aggregates feedback for `agentId`. Sums non-revoked values
         after normalising to the maximum valueDecimals found.
    @param agentId The agent to summarise.
    @param clients Client addresses to filter by (empty = all clients).
    @param tags Tags to filter by (empty = no tag filter).
    @return (totalValue, maxDecimals, activeCount, revokedCount).
    """
    client_list: DynArray[address, ARRAY_RETURN_MAX] = []
    if len(clients) == 0:
        client_list = self._clients[agentId]
    else:
        for c: address in clients:
            client_list.append(c)

    has_tag_filter: bool = len(tags) > 0

    # Pass 1: collect non-revoked values/decimals, find max, count.
    values: DynArray[int128, ARRAY_RETURN_MAX] = []
    decimals_list: DynArray[uint8, ARRAY_RETURN_MAX] = []
    max_decimals: uint8 = 0
    active_count: uint64 = 0
    revoked_count: uint64 = 0

    for client: address in client_list:
        last: uint256 = convert(self._last_index[agentId][client], uint256)
        for i: uint256 in range(last, bound=ARRAY_RETURN_MAX):
            idx: uint64 = convert(i + 1, uint64)
            entry: FeedbackEntry = self._feedback[agentId][client][idx]

            if has_tag_filter:
                if not self._in_tags(entry.tag1, tags) and not self._in_tags(entry.tag2, tags):
                    continue

            if entry.isRevoked:
                revoked_count += 1
            else:
                active_count += 1
                values.append(entry.value)
                decimals_list.append(entry.valueDecimals)
                if entry.valueDecimals > max_decimals:
                    max_decimals = entry.valueDecimals

    # Pass 2: normalise to maxDecimals and sum.
    total_value: int128 = 0
    for j: uint256 in range(len(values), bound=ARRAY_RETURN_MAX):
        scale: uint256 = 10 ** convert(max_decimals - decimals_list[j], uint256)
        total_value += values[j] * convert(scale, int128)

    return (total_value, max_decimals, active_count, revoked_count)


@external
@view
def getClients(agentId: uint256) -> DynArray[address, ARRAY_RETURN_MAX]:
    """
    @dev Returns the list of unique client addresses that have given
         feedback for `agentId`.
    @param agentId The agent identifier.
    @return DynArray of client addresses.
    """
    return self._clients[agentId]


@external
@view
def getLastIndex(agentId: uint256, clientAddress: address) -> uint64:
    """
    @dev Returns the last feedback index for the given
         (agentId, clientAddress) pair.
    @param agentId The agent identifier.
    @param clientAddress The client address.
    @return uint64 The last feedback index (0 if no feedback given).
    """
    return self._last_index[agentId][clientAddress]


@external
@pure
def getVersion() -> String[8]:
    """
    @dev Returns the version of this contract.
    @return String[8] The version string.
    """
    return "1.0.0"
