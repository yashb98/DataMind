"""
MCP Report Generator — SHA-256 Merkle tree for cryptographic provenance.
Day 11: Phase 2 — Verifiable AI: every claim in a report is hashed into a
tamper-evident Merkle tree whose root is stored on IPFS via Pinata.

Protocols: None (pure Python utility)
SOLID: SRP (Merkle logic only), OCP (extend MerkleTree subclass for new hash algos)
Benchmark: tests/benchmarks/bench_report.py
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class MerkleNode:
    """A single node in the Merkle binary tree.

    Attributes:
        hash: Hex-encoded SHA-256 digest for this node.
        left: Left child node (None for leaf nodes).
        right: Right child node (None for leaf nodes).
    """

    hash: str
    left: MerkleNode | None = field(default=None, repr=False)
    right: MerkleNode | None = field(default=None, repr=False)


class MerkleTree:
    """SHA-256 Merkle binary tree for cryptographic provenance of report claims.

    Each unique string in `claims` becomes a leaf node. Interior nodes combine
    their children's hashes via concatenation + SHA-256. The root hash serves
    as a tamper-evident fingerprint of the entire report content.

    Example:
        tree = MerkleTree(["Claim A", "Claim B", "Claim C"])
        root = tree.root_hash  # deterministic SHA-256 hex string
        proof = tree.get_proof(1)  # Merkle proof for "Claim B"
    """

    def __init__(self, claims: list[str]) -> None:
        """Initialise tree from a list of string claims.

        Args:
            claims: Ordered list of content strings to hash. May be empty.
        """
        self.claims = claims
        self._leaves: list[MerkleNode] = []
        self.root = self._build(claims)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _hash(data: str) -> str:
        """Return hex-encoded SHA-256 digest of data.

        Args:
            data: UTF-8 encodable string.

        Returns:
            64-character lowercase hex string.
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _build(self, items: list[str]) -> MerkleNode:
        """Build the Merkle tree from a flat list of claim strings.

        Args:
            items: List of leaf content strings.

        Returns:
            Root MerkleNode of the completed tree.
        """
        if not items:
            return MerkleNode(hash=self._hash("empty"))

        self._leaves = [MerkleNode(hash=self._hash(item)) for item in items]
        return self._build_tree(list(self._leaves))

    def _build_tree(self, nodes: list[MerkleNode]) -> MerkleNode:
        """Recursively combine pairs of nodes until a single root remains.

        Odd-length lists duplicate the last node to preserve a complete binary
        tree structure — identical to the Bitcoin Merkle tree convention.

        Args:
            nodes: Current level of tree nodes.

        Returns:
            Root MerkleNode.
        """
        if len(nodes) == 1:
            return nodes[0]

        # Duplicate last node when odd count (standard Merkle convention)
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])

        parents: list[MerkleNode] = []
        for i in range(0, len(nodes), 2):
            combined = nodes[i].hash + nodes[i + 1].hash
            parent = MerkleNode(
                hash=self._hash(combined),
                left=nodes[i],
                right=nodes[i + 1],
            )
            parents.append(parent)

        return self._build_tree(parents)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def root_hash(self) -> str:
        """Hex-encoded SHA-256 root hash representing the entire claim set.

        Returns:
            64-character lowercase hex string.
        """
        return self.root.hash

    def get_proof(self, claim_index: int) -> list[str]:
        """Return the Merkle inclusion proof for the claim at `claim_index`.

        The proof is a list of sibling hashes at each level from the leaf up
        to (but not including) the root. A verifier can recompute the root by
        repeatedly hashing the claim with each sibling in order.

        Args:
            claim_index: Zero-based index into the original `claims` list.

        Returns:
            List of sibling hex hashes (leaf → root direction). Empty list if
            the tree has a single node or the index is out of range.

        Raises:
            IndexError: If claim_index is negative or >= len(claims).
        """
        if not self.claims:
            return []

        if claim_index < 0 or claim_index >= len(self.claims):
            raise IndexError(
                f"claim_index {claim_index} out of range for {len(self.claims)} claims"
            )

        proof: list[str] = []
        # Rebuild current level as hash strings for traversal
        current_level = [MerkleNode(hash=self._hash(c)) for c in self.claims]
        if len(current_level) % 2 == 1:
            current_level.append(current_level[-1])

        idx = claim_index

        while len(current_level) > 1:
            # Sibling is the adjacent node in the pair
            if idx % 2 == 0:
                sibling_idx = idx + 1
            else:
                sibling_idx = idx - 1

            sibling_idx = min(sibling_idx, len(current_level) - 1)
            proof.append(current_level[sibling_idx].hash)

            # Advance to parent level
            next_level: list[MerkleNode] = []
            for i in range(0, len(current_level), 2):
                combined = current_level[i].hash + current_level[min(i + 1, len(current_level) - 1)].hash
                next_level.append(MerkleNode(hash=self._hash(combined)))

            if len(next_level) % 2 == 1 and len(next_level) > 1:
                next_level.append(next_level[-1])

            idx //= 2
            current_level = next_level

        return proof

    def verify_claim(self, claim: str, proof: list[str]) -> bool:
        """Verify that `claim` is included in this tree using `proof`.

        Recomputes the root hash by combining the claim's hash with each
        sibling in the proof path and checks against `self.root_hash`.

        Args:
            claim: Original claim string.
            proof: Merkle proof as returned by `get_proof`.

        Returns:
            True if the computed root matches `self.root_hash`.
        """
        current_hash = self._hash(claim)
        for sibling_hash in proof:
            # Convention: always hash in lexicographic order to ensure
            # determinism regardless of left/right position
            if current_hash <= sibling_hash:
                current_hash = self._hash(current_hash + sibling_hash)
            else:
                current_hash = self._hash(sibling_hash + current_hash)
        return current_hash == self.root_hash


def build_report_claims(title: str, sections: list[dict]) -> list[str]:
    """Construct the ordered list of provenance claims for a report.

    Each claim represents an atomic piece of content: the report title,
    every section heading, and every section body text. Tables (data rows)
    are serialised as sorted key=value strings per row.

    Args:
        title: Report title string.
        sections: List of section dicts with "heading", "content", and
            optional "data" keys.

    Returns:
        Ordered list of claim strings suitable for MerkleTree construction.
    """
    claims: list[str] = [f"title:{title}"]

    for section in sections:
        heading = section.get("heading", "")
        content = section.get("content", "")
        claims.append(f"heading:{heading}")
        claims.append(f"content:{content}")

        data = section.get("data") or []
        for row in data:
            # Serialise row as sorted key=value pairs for determinism
            row_str = ",".join(f"{k}={v}" for k, v in sorted(row.items()))
            claims.append(f"data_row:{row_str}")

    return claims
