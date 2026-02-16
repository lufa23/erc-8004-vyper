# pragma version ~=0.4.3
"""
@title ERC-8004 Validation Registry
@custom:contract-name ValidationRegistry
@license UNLICENSED
@notice On-chain validation system for ERC-8004 agents.
        Tracks validation requests per (agentId, requester) pair
        and validator responses with valid/invalid outcomes.
        References the Identity Registry for agent existence and
        ownership checks via staticcall.
"""


from interfaces import IIdentityRegistry


# @dev Max-size constants (UPPER_SNAKE_CASE, no leading underscore).
TAG_MAX: constant(uint256) = 64
LINK_MAX: constant(uint256) = 512
ARRAY_RETURN_MAX: constant(uint256) = 1024
FILTER_ARRAY_MAX: constant(uint256) = 128


event ValidationRequested:
    agentId: indexed(uint256)
    requester: indexed(address)
    requestIndex: uint64
    requestURI: String[LINK_MAX]
    requestHash: bytes32
    indexedTag: indexed(String[TAG_MAX])
    tag: String[TAG_MAX]


event ValidationResponseSubmitted:
    agentId: indexed(uint256)
    requester: indexed(address)
    requestIndex: indexed(uint64)
    validator: address
    isValid: bool
    responseURI: String[LINK_MAX]
    responseHash: bytes32


# @dev Address of the IdentityRegistry contract, set once at deploy time.
_IDENTITY_REGISTRY: immutable(IIdentityRegistry)


# @dev Last request index per (agentId, requester) pair. 1-indexed.
_last_request_index: HashMap[uint256, HashMap[address, uint64]]


# @dev Tag stored per validation request.
_request_tag: HashMap[uint256, HashMap[address, HashMap[uint64, String[TAG_MAX]]]]


# @dev Total response count per validation request.
_response_count: HashMap[uint256, HashMap[address, HashMap[uint64, uint64]]]


# @dev Count of "valid" responses per validation request.
_valid_count: HashMap[uint256, HashMap[address, HashMap[uint64, uint64]]]


# @dev Count of "invalid" responses per validation request.
_invalid_count: HashMap[uint256, HashMap[address, HashMap[uint64, uint64]]]


# @dev Whether a validator has already responded to a request.
_has_validated: HashMap[uint256, HashMap[address, HashMap[uint64, HashMap[address, bool]]]]


@deploy
@payable
def __init__(identityRegistry_: address):
    """
    @dev To omit the opcodes for checking the `msg.value`
         in the creation-time EVM bytecode, the constructor
         is declared as `payable`.
    @notice Initialises the Validation Registry with a reference
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
def validationRequest(
    agentId: uint256,
    requestURI: String[LINK_MAX] = "",
    requestHash: bytes32 = empty(bytes32),
    tag: String[TAG_MAX] = "",
) -> uint64:
    """
    @dev Submits a validation request for `agentId`. The agent must
         exist in the Identity Registry. Requests are indexed per
         (agentId, msg.sender) pair with 1-based indices.
    @param agentId The agent to request validation for.
    @param requestURI URI pointing to off-chain request content (optional).
    @param requestHash keccak256 of content at requestURI (optional).
    @param tag Tag for categorisation (optional, stored on-chain).
    @return uint64 The newly assigned request index.
    """
    owner: address = staticcall _IDENTITY_REGISTRY.ownerOf(agentId)

    idx: uint64 = self._last_request_index[agentId][msg.sender] + 1
    self._last_request_index[agentId][msg.sender] = idx

    self._request_tag[agentId][msg.sender][idx] = tag

    log ValidationRequested(
        agentId=agentId,
        requester=msg.sender,
        requestIndex=idx,
        requestURI=requestURI,
        requestHash=requestHash,
        indexedTag=tag,
        tag=tag,
    )

    return idx


@external
def validationResponse(
    agentId: uint256,
    requester: address,
    requestIndex: uint64,
    isValid: bool,
    responseURI: String[LINK_MAX] = "",
    responseHash: bytes32 = empty(bytes32),
):
    """
    @dev Submits a validation response for an existing request.
         Anyone can respond, but each address may only respond
         once per request.
    @param agentId The agent the request was made for.
    @param requester The address that submitted the request.
    @param requestIndex The 1-based index of the request.
    @param isValid Whether the validation outcome is valid.
    @param responseURI URI pointing to off-chain response content (optional).
    @param responseHash keccak256 of content at responseURI (optional).
    """
    assert requestIndex > 0 and requestIndex <= self._last_request_index[agentId][requester], "ValidationRegistry: request does not exist"
    assert not self._has_validated[agentId][requester][requestIndex][msg.sender], "ValidationRegistry: already validated"

    self._has_validated[agentId][requester][requestIndex][msg.sender] = True
    self._response_count[agentId][requester][requestIndex] += 1

    if isValid:
        self._valid_count[agentId][requester][requestIndex] += 1
    else:
        self._invalid_count[agentId][requester][requestIndex] += 1

    log ValidationResponseSubmitted(
        agentId=agentId,
        requester=requester,
        requestIndex=requestIndex,
        validator=msg.sender,
        isValid=isValid,
        responseURI=responseURI,
        responseHash=responseHash,
    )


@external
@view
def getResponseCount(agentId: uint256, requester: address, requestIndex: uint64) -> uint64:
    """
    @dev Returns the total number of responses for a validation request.
    @param agentId The agent identifier.
    @param requester The address that submitted the request.
    @param requestIndex The 1-based index of the request.
    @return uint64 The total response count.
    """
    return self._response_count[agentId][requester][requestIndex]


@external
@view
def getValidCount(agentId: uint256, requester: address, requestIndex: uint64) -> uint64:
    """
    @dev Returns the number of "valid" responses for a validation request.
    @param agentId The agent identifier.
    @param requester The address that submitted the request.
    @param requestIndex The 1-based index of the request.
    @return uint64 The valid response count.
    """
    return self._valid_count[agentId][requester][requestIndex]


@external
@view
def getInvalidCount(agentId: uint256, requester: address, requestIndex: uint64) -> uint64:
    """
    @dev Returns the number of "invalid" responses for a validation request.
    @param agentId The agent identifier.
    @param requester The address that submitted the request.
    @param requestIndex The 1-based index of the request.
    @return uint64 The invalid response count.
    """
    return self._invalid_count[agentId][requester][requestIndex]


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
def getSummary(
    agentId: uint256,
    requester: address,
    tags: DynArray[String[TAG_MAX], FILTER_ARRAY_MAX] = [],
) -> (uint64, uint64, uint64):
    """
    @dev Aggregates validation counts across all requests from
         `requester` for `agentId`, optionally filtered by tags.
    @param agentId The agent identifier.
    @param requester The address that submitted the requests.
    @param tags Tags to filter by (empty = no filter).
    @return (totalResponses, totalValid, totalInvalid).
    """
    last: uint256 = convert(self._last_request_index[agentId][requester], uint256)
    has_tag_filter: bool = len(tags) > 0

    total_responses: uint64 = 0
    total_valid: uint64 = 0
    total_invalid: uint64 = 0

    for i: uint256 in range(last, bound=ARRAY_RETURN_MAX):
        idx: uint64 = convert(i + 1, uint64)

        if has_tag_filter:
            if not self._in_tags(self._request_tag[agentId][requester][idx], tags):
                continue

        total_responses += self._response_count[agentId][requester][idx]
        total_valid += self._valid_count[agentId][requester][idx]
        total_invalid += self._invalid_count[agentId][requester][idx]

    return (total_responses, total_valid, total_invalid)


@external
@view
def getLastRequestIndex(agentId: uint256, requester: address) -> uint64:
    """
    @dev Returns the last request index for the given
         (agentId, requester) pair.
    @param agentId The agent identifier.
    @param requester The requester address.
    @return uint64 The last request index (0 if no requests made).
    """
    return self._last_request_index[agentId][requester]


@external
@pure
def getVersion() -> String[8]:
    """
    @dev Returns the version of this contract.
    @return String[8] The version string.
    """
    return "1.0.0"
