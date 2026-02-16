# ERC-8004 Spec Notes for Vyper Implementation

Source: https://eips.ethereum.org/EIPS/eip-8004
Status: Draft ERC, live on mainnet since Jan 29, 2026.
Requires: EIP-155, EIP-712, ERC-721, ERC-1271.


## Identity Registry

ERC-721 + URIStorage. `agentId` = tokenId, `agentURI` = tokenURI.

### Struct

```
MetadataEntry { metadataKey: string, metadataValue: bytes }
```

### Functions

```
register() → uint256 agentId
register(string agentURI) → uint256 agentId
register(string agentURI, MetadataEntry[] metadata) → uint256 agentId
setAgentURI(uint256 agentId, string newURI)
getMetadata(uint256 agentId, string metadataKey) → bytes
setMetadata(uint256 agentId, string metadataKey, bytes metadataValue)
setAgentWallet(uint256 agentId, address newWallet, uint256 deadline, bytes signature)
getAgentWallet(uint256 agentId) → address
unsetAgentWallet(uint256 agentId)
```

Plus ERC-721 inherited functions.

### Events

```
Registered(uint256 indexed agentId, string agentURI, address indexed owner)
URIUpdated(uint256 indexed agentId, string newURI, address indexed updatedBy)
MetadataSet(uint256 indexed agentId, string indexed indexedMetadataKey, string metadataKey, bytes metadataValue)
```

### Behavioral rules

- `agentWallet` is a reserved metadata key. Cannot be set via `setMetadata()` or during `register()`.
- On `register()`, `agentWallet` is set to `msg.sender`.
- `setAgentWallet` verifies EIP-712 signature (EOA) or ERC-1271 (contract wallet) from `newWallet`.
- On transfer, `agentWallet` is cleared to `address(0)`.
- `register()` emits: Transfer, MetadataSet (agentWallet), one MetadataSet per extra entry, Registered.
- Only owner or approved operator can call setAgentURI, setMetadata, unsetAgentWallet, setAgentWallet.


## Reputation Registry

### Functions

```
initialize(address identityRegistry_)  # see "initialize vs __init__" decision below
getIdentityRegistry() → address
giveFeedback(uint256 agentId, int128 value, uint8 valueDecimals, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)
revokeFeedback(uint256 agentId, uint64 feedbackIndex)
appendResponse(uint256 agentId, address clientAddress, uint64 feedbackIndex, string responseURI, bytes32 responseHash)
getSummary(uint256 agentId, address[] clientAddresses, string tag1, string tag2) → (uint64 count, int128 summaryValue, uint8 summaryValueDecimals)
readFeedback(uint256 agentId, address clientAddress, uint64 feedbackIndex) → (int128 value, uint8 valueDecimals, string tag1, string tag2, bool isRevoked)
readAllFeedback(uint256 agentId, address[] clientAddresses, string tag1, string tag2, bool includeRevoked) → (address[] clients, uint64[] feedbackIndexes, int128[] values, uint8[] valueDecimals, string[] tag1s, string[] tag2s, bool[] revokedStatuses)
getResponseCount(uint256 agentId, address clientAddress, uint64 feedbackIndex, address[] responders) → uint64
getClients(uint256 agentId) → address[]
getLastIndex(uint256 agentId, address clientAddress) → uint64
```

### Events

```
NewFeedback(uint256 indexed agentId, address indexed clientAddress, uint64 feedbackIndex, int128 value, uint8 valueDecimals, string indexed indexedTag1, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)
FeedbackRevoked(uint256 indexed agentId, address indexed clientAddress, uint64 indexed feedbackIndex)
ResponseAppended(uint256 indexed agentId, address indexed clientAddress, uint64 feedbackIndex, address indexed responder, string responseURI, bytes32 responseHash)
```

### Behavioral rules

- `valueDecimals` MUST be 0–18.
- Submitter MUST NOT be agent owner or approved operator.
- `agentId` must exist in the Identity Registry.
- `tag1`, `tag2`, `endpoint`, `feedbackURI`, `feedbackHash` are OPTIONAL (empty string / zero bytes).
- `feedbackHash` is keccak256 of content at `feedbackURI`. OPTIONAL for IPFS/content-addressed URIs (pass `bytes32(0)`). Same for `responseHash` in `appendResponse`.
- Agents giving feedback SHOULD use their on-chain `agentWallet` address.
- Stored: value, valueDecimals, tag1, tag2, isRevoked, feedbackIndex.
- Emitted only: endpoint, feedbackURI, feedbackHash.
- `feedbackIndex` is 1-indexed per (clientAddress, agentId) pair.
- Only original clientAddress can revoke.
- Anyone can appendResponse.
- `getSummary` requires non-empty clientAddresses.
- `readAllFeedback`: `agentId` is the only mandatory parameter. `clientAddresses` (pass `[]` for all clients), `tag1`/`tag2` (pass `""` to skip), `includeRevoked` are optional filters. Revoked feedback omitted by default.
- `getResponseCount`: `agentId` is the only mandatory parameter. `clientAddress` (pass `address(0)` for all), `feedbackIndex` (pass `0` for all), `responders` (pass `[]` for all) are optional filters.


## Validation Registry

Still under active update per the official repo README ("under active update and discussion with the TEE community"). No mainnet deployment addresses listed yet — only Identity and Reputation registries are deployed.

### Functions

```
initialize(address identityRegistry_)  # see "initialize vs __init__" decision below
getIdentityRegistry() → address
validationRequest(address validatorAddress, uint256 agentId, string requestURI, bytes32 requestHash)
validationResponse(bytes32 requestHash, uint8 response, string responseURI, bytes32 responseHash, string tag)
getValidationStatus(bytes32 requestHash) → (address validatorAddress, uint256 agentId, uint8 response, bytes32 responseHash, string tag, uint256 lastUpdate)
getSummary(uint256 agentId, address[] validatorAddresses, string tag) → (uint64 count, uint8 averageResponse)
getAgentValidations(uint256 agentId) → bytes32[]
getValidatorRequests(address validatorAddress) → bytes32[]
```

### Events

```
ValidationRequest(address indexed validatorAddress, uint256 indexed agentId, string requestURI, bytes32 indexed requestHash)
ValidationResponse(address indexed validatorAddress, uint256 indexed agentId, bytes32 indexed requestHash, uint8 response, string responseURI, bytes32 responseHash, string tag)
```

### Behavioral rules

- `validationRequest` MUST be called by owner or operator of agentId.
- `validationResponse` MUST be called by the validatorAddress from the original request.
- response: 0–100.
- `responseURI`, `responseHash`, `tag` are OPTIONAL in `validationResponse`. `responseHash` is keccak256 of content at `responseURI`. OPTIONAL for IPFS/content-addressed URIs (pass `bytes32(0)`).
- `requestHash` is caller-computed keccak256 of the request payload. Stored on-chain as primary key. Must be unique per request.
- `validationResponse` can be called multiple times per requestHash (progressive validation).
- `getSummary`: `agentId` is the only mandatory parameter. `validatorAddresses` (pass `[]` for all), `tag` (pass `""` to skip) are optional filters.
- Stored: requestHash, validatorAddress, agentId, response, responseHash, lastUpdate, tag.


## Vyper-specific notes

### register() overloading

Default parameters produce N+1 selectors. Single function covers all three overloads:

```vyper
@external
def register(agentURI: String[URI_MAX] = "", metadata: DynArray[MetadataEntry, 16] = []) -> uint256:
    ...
```

Selectors: `register()`, `register(string)`, `register(string,(string,bytes)[])`.

**Risk**: No Vyper test coverage for `DynArray[Struct, N] = []` as default param. Code path analysis of 0.4.3 says it should work. Verify at compile time before building on this assumption. Fallback: separate `_register_internal` called by multiple external entry points.

### Naming conventions

Compiler enforces nothing beyond `^[_a-zA-Z][a-zA-Z0-9_]*$` and reserved keywords. We follow Snekmate's conventions:

| Element | Convention | Example |
|---------|-----------|---------|
| External functions (EIP-defined) | camelCase | `setAgentWallet`, `giveFeedback`, `validationRequest` |
| External functions (custom) | snake_case | `safe_mint`, `set_minter` |
| Internal functions | _snake_case | `_clear_agent_wallet`, `_check_owner_or_approved` |
| Events | PascalCase | `Registered`, `MetadataSet`, `NewFeedback` |
| Private state vars | _snake_case | `_metadata`, `_agent_wallets`, `_feedback` |
| Public state vars (ERC getter) | camelCase | `balanceOf`, `isApprovedForAll` |
| Constants | _UPPER_SNAKE_CASE | `_AGENT_WALLET_SET_TYPEHASH`, `_SUPPORTED_INTERFACES` |
| Max-size constants | UPPER_SNAKE_CASE | `URI_MAX`, `KEY_MAX`, `ARRAY_RETURN_MAX` |

All EIP-8004 external functions are ABI-facing, so all use camelCase. Full list:

**Identity Registry**: `register`, `setAgentURI`, `getMetadata`, `setMetadata`, `setAgentWallet`, `getAgentWallet`, `unsetAgentWallet` (plus ERC-721: `transferFrom`, `safeTransferFrom`, `approve`, `setApprovalForAll`, `balanceOf`, `ownerOf`, `getApproved`, `isApprovedForAll`, `tokenURI`, `totalSupply`, `tokenByIndex`, `tokenOfOwnerByIndex`)

**Reputation Registry**: `initialize`, `getIdentityRegistry`, `giveFeedback`, `revokeFeedback`, `appendResponse`, `getSummary`, `readFeedback`, `readAllFeedback`, `getResponseCount`, `getClients`, `getLastIndex`

**Validation Registry**: `initialize`, `getIdentityRegistry`, `validationRequest`, `validationResponse`, `getValidationStatus`, `getSummary`, `getAgentValidations`, `getValidatorRequests`

### ERC-721 base — [DECISION NEEDED]

Snekmate v0.1.2 `erc721.vy` (Vyper ~0.4.3). `_before_token_transfer` and `_after_token_transfer` are `@internal` in the module — no virtual/override in Vyper modules.

We must auto-clear `agentWallet` on every transfer. Two options:

**(a) Fork `erc721.vy`**: Add clearing into `_before_token_transfer`. Single hook point, but must track upstream.

**(b) Wrap transfer functions**: Selectively export, write our own `transferFrom`/`safeTransferFrom` that call `erc721._transfer(...)` then clear. No fork, but must wrap every transfer path.

### initialize() vs __init__ — [DECISION NEEDED]

The Solidity reference uses UUPS upgradeable proxies — all three contracts have `initialize()` instead of constructors. A non-upgradeable Vyper contract would use `__init__` (deployed via `@deploy`), which means no `initialize` function in the ABI.

**(a) `__init__`**: Simpler. No initialization guard needed. But produces a different ABI — no `initialize(address)` selector. Callers expecting the Solidity interface will break.

**(b) `initialize()`**: Matches Solidity ABI. Requires a manual `_initialized: bool` guard (or Snekmate's `initializable` module if available). Reputation and Validation registries take `identityRegistry_` as the init param; Identity Registry takes ERC-721 name/symbol + EIP-712 domain params.

### DynArray max sizes

| Constant | Value | Used for |
|----------|-------|----------|
| URI_MAX | 2048 | agentURI, newURI (data: base64 URIs) |
| KEY_MAX | 64 | metadataKey |
| TAG_MAX | 64 | tag1, tag2, tag |
| LINK_MAX | 512 | endpoint, feedbackURI, responseURI, requestURI |
| VALUE_MAX | 1024 | metadataValue (bytes) |
| SIG_MAX | 256 | signature (ERC-1271) |
| ARRAY_RETURN_MAX | 1024 | returned DynArrays |
| FILTER_ARRAY_MAX | 128 | input filter arrays |

Exceeding MAX reverts. May need pagination later.

### EIP-712 / ERC-1271

Use Snekmate v0.1.2 modules:

- `eip712_domain_separator.vy`: `_hash_typed_data_v4(struct_hash) → bytes32`. Caches domain separator, handles chain ID / address changes.
- `ecdsa.vy`: `_recover_vrs(hash, v, r, s) → address`.
- `signature_checker.vy`: `_is_valid_ERC1271_signature_now(signer, hash, signature) → bool`. Uses `raw_call(..., revert_on_failure=False, is_static_call=True)`.

Type hash for `setAgentWallet` — [VERIFY AGAINST SOLIDITY REF]:
```
_AGENT_WALLET_SET_TYPEHASH: constant(bytes32) = keccak256("AgentWalletSet(uint256 agentId,address newWallet,address owner,uint256 deadline)")
```
The EIP does not define the type hash string. The Solidity reference (`IdentityRegistryUpgradeable.sol`) uses `AgentWalletSet` with fields `(agentId, newWallet, owner, deadline)` — no nonce. Replay protection uses a tight deadline (max 5 minutes into the future). Domain name: `"ERC8004IdentityRegistry"`, version: `"1"`. Verify this is still current before implementing.

### readAllFeedback return type

Returns 7 parallel DynArrays. Required for ABI compat — DynArray of structs would produce a different selector.

### Indexed strings in events

`string indexed` params (indexedMetadataKey, indexedTag1) are stored as keccak256 in topics. Spec includes both indexed and non-indexed copies of the same data.

### Reentrancy

`@nonreentrant` on functions with external call vectors:
- `register` — `_safeMint` callback to receiver.
- `setAgentWallet` — ERC-1271 `isValidSignature` call to contract wallet.

Not globally via pragma. In 0.4.2+, `@nonreentrant` functions cannot call other `@nonreentrant` functions — targeted decorators avoid this constraint.

### Vyper 0.4.x syntax

- `extcall` / `staticcall` for external calls (bare calls removed).
- Keyword-only struct instantiation: `MetadataEntry(metadataKey=key, metadataValue=value)`.
- Keyword-only event emission: `log MetadataSet(agentId=id, indexedMetadataKey=key, metadataKey=key, metadataValue=value)`. Positional args deprecated since 0.4.1, will be disallowed in a future release.
- `flag` replaces `enum`.
- Typed loop variables: `for entry: MetadataEntry in metadata:`.
- Module system: `uses:`, `initializes:`, `exports:`. Dependency injection: `initializes: erc721[ownable := ow]`.


## Repo structure

```
erc-8004-vyper/
├── contracts/
│   ├── IdentityRegistry.vy
│   ├── ReputationRegistry.vy
│   ├── ValidationRegistry.vy
│   └── interfaces/
│       ├── IERC1271.vy
│       └── IIdentityRegistry.vy
├── tests/
│   ├── conftest.py
│   ├── test_identity_registry.py
│   ├── test_reputation_registry.py
│   ├── test_validation_registry.py
│   └── test_integration.py
├── scripts/
│   └── deploy.py
├── moccasin.toml
└── README.md
```
