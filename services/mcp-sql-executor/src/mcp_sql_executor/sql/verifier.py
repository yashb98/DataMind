"""
MCP SQL Executor — Anti-Hallucination Layer 8: Numerical Verification.
Day 8: Zero tolerance for hallucinated statistics — re-verifies all numbers against source.

Protocols: None (internal component)
SOLID: SRP (verification only), OCP (new verification strategy = new class)
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from mcp_sql_executor.models import DatabaseTarget, VerifyNumbersResponse
from mcp_sql_executor.sql.executor import ISQLExecutor

log = structlog.get_logger(__name__)


class NumberVerifier:
    """Re-executes aggregation SQL to verify claimed numerical values.

    Anti-hallucination Layer 8: Zero tolerance for hallucinated stats.
    Any discrepancy > tolerance threshold returns MISMATCH verdict.
    """

    def __init__(self, executor_router: Any) -> None:
        self._router = executor_router

    async def verify(
        self,
        claim: str,
        verification_sql: str,
        database: DatabaseTarget,
        tenant_id: str,
        tolerance: float = 0.01,
    ) -> VerifyNumbersResponse:
        """Verify a numerical claim by re-executing the source query.

        Args:
            claim: The claim to verify (e.g., "total revenue is $1.2M").
            verification_sql: SQL that recomputes the claimed figure.
            database: Database to query.
            tenant_id: Tenant identifier.
            tolerance: Relative tolerance for acceptable discrepancy (default 1%).

        Returns:
            VerifyNumbersResponse with verdict and discrepancy details.
        """
        claimed = _extract_number_from_claim(claim)
        executor: ISQLExecutor = self._router.get_executor(database)

        try:
            result = await executor.execute(
                sql=verification_sql,
                tenant_id=tenant_id,
                parameters=None,
                max_rows=1,
                timeout_s=30,
            )
        except Exception as exc:
            log.error("verifier.execute_failed", error=str(exc), tenant_id=tenant_id)
            return VerifyNumbersResponse(
                verified=False,
                claimed_value=claimed,
                actual_value=None,
                discrepancy_pct=None,
                verdict="ERROR",
                details=f"Verification query failed: {exc}",
            )

        if not result.rows:
            return VerifyNumbersResponse(
                verified=False,
                claimed_value=claimed,
                actual_value=None,
                discrepancy_pct=None,
                verdict="INSUFFICIENT_DATA",
                details="Verification query returned no rows.",
            )

        # Extract first numeric value from first row
        actual = _extract_first_number(result.rows[0])
        if actual is None:
            return VerifyNumbersResponse(
                verified=False,
                claimed_value=claimed,
                actual_value=None,
                discrepancy_pct=None,
                verdict="INSUFFICIENT_DATA",
                details=f"Could not extract numeric value from row: {result.rows[0]}",
            )

        if claimed is None:
            # No claimed number to compare — just return the actual value
            return VerifyNumbersResponse(
                verified=True,
                claimed_value=None,
                actual_value=actual,
                discrepancy_pct=None,
                verdict="VERIFIED",
                details=f"Actual value from source: {actual}",
            )

        discrepancy_pct = abs(actual - claimed) / max(abs(claimed), 1e-9)
        verified = discrepancy_pct <= tolerance

        verdict = "VERIFIED" if verified else "MISMATCH"
        details = (
            f"Claimed: {claimed:,.4f} | Actual: {actual:,.4f} | "
            f"Discrepancy: {discrepancy_pct * 100:.2f}% | Tolerance: {tolerance * 100:.1f}%"
        )

        log.info(
            "verifier.result",
            tenant_id=tenant_id,
            verdict=verdict,
            claimed=claimed,
            actual=actual,
            discrepancy_pct=round(discrepancy_pct * 100, 4),
        )

        return VerifyNumbersResponse(
            verified=verified,
            claimed_value=claimed,
            actual_value=actual,
            discrepancy_pct=round(discrepancy_pct * 100, 4),
            verdict=verdict,
            details=details,
        )


# ── Parsing Helpers ───────────────────────────────────────────────────────────


def _extract_number_from_claim(claim: str) -> float | None:
    """Extract the first meaningful number from a natural language claim.

    Handles currency symbols, K/M/B suffixes, and percentage signs.

    Args:
        claim: Natural language string containing a number.

    Returns:
        Extracted float value, or None if not found.
    """
    # Strip currency symbols and commas
    cleaned = re.sub(r"[$€£¥,]", "", claim)

    # Match number with optional K/M/B/T suffix
    pattern = r"(\d+(?:\.\d+)?)\s*([KMBTkmbt]?)"
    matches = re.findall(pattern, cleaned)
    if not matches:
        return None

    value_str, suffix = matches[0]
    value = float(value_str)

    multipliers = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}
    if suffix.lower() in multipliers:
        value *= multipliers[suffix.lower()]

    return value


def _extract_first_number(row: dict[str, Any]) -> float | None:
    """Extract the first numeric value from a database result row.

    Args:
        row: Dict mapping column name to value.

    Returns:
        First numeric value found, or None.
    """
    for val in row.values():
        if isinstance(val, (int, float)) and val is not None:
            return float(val)
        if isinstance(val, str):
            try:
                return float(val.replace(",", ""))
            except ValueError:
                continue
    return None
