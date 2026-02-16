# erc-8004-vyper

Vyper reference implementation of [ERC-8004: Trustless Agents](https://eips.ethereum.org/EIPS/eip-8004).

Three contracts:
- **IdentityRegistry** — ERC-721 agent registration, metadata, wallet verification (EIP-712 / ERC-1271)
- **ReputationRegistry** — feedback, revocation, response tracking, on-chain summaries
- **ValidationRegistry** — validation request/response lifecycle

Built with [Moccasin](https://github.com/Cyfrin/moccasin), [Snekmate](https://github.com/pcaversaccio/snekmate), and [Titanoboa](https://github.com/vyperlang/titanoboa).

## Status

Work in progress. Targeting the current EIP text at eips.ethereum.org.

## Reference

- [EIP-8004 spec](https://eips.ethereum.org/EIPS/eip-8004)
- [Official Solidity reference implementation](https://github.com/erc-8004/erc-8004-contracts)
- [Cairo port](https://github.com/Akashneelesh/erc8004-cairo)
