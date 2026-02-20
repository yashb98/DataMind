"""
Sensitivity Detector — classifies data sensitivity level.
Determines whether data/query can be sent to cloud LLMs or must stay local.

GDPR-critical: if sensitivity = CONFIDENTIAL or RESTRICTED → cloud LLM blocked.
"""
import re

import structlog

from slm_router.models import SensitivityLevel

log = structlog.get_logger(__name__)

# PII patterns (lightweight — Presidio does the heavy lifting on data)
_PII_PATTERNS = [
    re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'),  # email
    re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),                            # phone
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),                                    # SSN
    re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\b'),         # credit card
    re.compile(r'\b[A-Z]{2}\d{6}[A-Z]\b'),                                   # passport (UK)
]

# Keywords indicating sensitive data domains
_RESTRICTED_KEYWORDS = {
    "ssn", "social security", "passport", "credit card", "bank account",
    "national insurance", "ni number", "medical record", "diagnosis",
    "prescription", "patient", "salary", "payroll", "compensation",
    "personal email", "home address", "date of birth", "dob",
}

_CONFIDENTIAL_KEYWORDS = {
    "employee", "staff", "hr data", "performance review", "disciplinary",
    "financial report", "revenue", "profit", "margin", "ebitda",
    "customer pii", "user data", "personal data", "private", "confidential",
    "internal only", "trade secret", "ip address", "access log",
}

_INTERNAL_KEYWORDS = {
    "internal", "company data", "proprietary", "non-public",
    "customer list", "vendor", "contract",
}


class RuleBasedSensitivityDetector:
    """
    SRP: Only classifies sensitivity.
    Rule-based (no SLM needed) — fast, deterministic, auditable.
    Presidio handles actual PII masking; this handles routing decisions.
    """

    def detect(self, query: str) -> tuple[SensitivityLevel, float]:
        """Returns (sensitivity_level, confidence)."""
        q = query.lower()

        # Check for direct PII in the query text
        for pattern in _PII_PATTERNS:
            if pattern.search(query):
                log.warning("sensitivity.pii_detected_in_query", pattern=pattern.pattern[:30])
                return SensitivityLevel.RESTRICTED, 0.98

        # Keyword matching
        if any(kw in q for kw in _RESTRICTED_KEYWORDS):
            return SensitivityLevel.RESTRICTED, 0.90

        if any(kw in q for kw in _CONFIDENTIAL_KEYWORDS):
            return SensitivityLevel.CONFIDENTIAL, 0.82

        if any(kw in q for kw in _INTERNAL_KEYWORDS):
            return SensitivityLevel.INTERNAL, 0.75

        return SensitivityLevel.PUBLIC, 0.88
