"""
SLM Router unit tests — fast, no external dependencies.
Tests classification logic and routing decisions without calling Ollama.
"""
import pytest

from slm_router.classifiers.intent import _rule_based_classify
from slm_router.classifiers.complexity import _heuristic_complexity
from slm_router.classifiers.sensitivity import RuleBasedSensitivityDetector
from slm_router.models import (
    ComplexityLevel,
    IntentLabel,
    InferenceTier,
    SensitivityLevel,
)
from slm_router.router import _determine_tier


# ---- Intent classifier tests -----------------------------------------------
class TestRuleBasedIntent:
    def test_sql_query(self):
        label, conf = _rule_based_classify("Show me all customers from the database with SQL")
        assert label == IntentLabel.SQL
        assert conf >= 0.60

    def test_forecast_query(self):
        label, _ = _rule_based_classify("Predict next quarter revenue using Prophet")
        assert label == IntentLabel.FORECAST

    def test_anomaly_query(self):
        label, _ = _rule_based_classify("Detect outliers and anomalies in the sales data")
        assert label == IntentLabel.ANOMALY

    def test_visualise_query(self):
        label, _ = _rule_based_classify("Create a bar chart of revenue by region")
        assert label == IntentLabel.VISUALISE

    def test_report_query(self):
        label, _ = _rule_based_classify("Generate a monthly executive summary report")
        assert label == IntentLabel.REPORT

    def test_eda_query(self):
        label, _ = _rule_based_classify("Show me the distribution and statistics of the dataset")
        assert label == IntentLabel.EDA

    def test_general_query(self):
        label, conf = _rule_based_classify("Hello, how are you?")
        assert label == IntentLabel.GENERAL
        assert conf >= 0.50


# ---- Complexity scorer tests -----------------------------------------------
class TestHeuristicComplexity:
    def test_simple_query(self):
        score, level = _heuristic_complexity("Show total sales for last month")
        assert level == ComplexityLevel.SIMPLE
        assert score <= 0.35

    def test_medium_query(self):
        score, level = _heuristic_complexity(
            "Compare revenue breakdown by region vs last year trend"
        )
        assert level in (ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX)

    def test_expert_query(self):
        score, level = _heuristic_complexity(
            "Build a causal inference model to explain why churn increased. "
            "Account for confounders like seasonality, correlation between variables, "
            "and run a hypothesis test to verify statistical significance of results."
        )
        assert level in (ComplexityLevel.COMPLEX, ComplexityLevel.EXPERT)
        assert score >= 0.50


# ---- Sensitivity detector tests --------------------------------------------
class TestSensitivityDetector:
    def setup_method(self):
        self.detector = RuleBasedSensitivityDetector()

    def test_public_query(self):
        level, conf = self.detector.detect("Show me total revenue by product")
        assert level == SensitivityLevel.PUBLIC
        assert conf >= 0.80

    def test_pii_email_detected(self):
        level, conf = self.detector.detect("Find records for john.doe@example.com")
        assert level == SensitivityLevel.RESTRICTED
        assert conf >= 0.95

    def test_restricted_ssn(self):
        level, _ = self.detector.detect("Show me salary and SSN for all employees")
        assert level == SensitivityLevel.RESTRICTED

    def test_confidential_hr(self):
        level, _ = self.detector.detect("Show performance review data for staff")
        assert level in (SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED)

    def test_internal_data(self):
        level, _ = self.detector.detect("Show internal vendor contract data")
        assert level in (SensitivityLevel.INTERNAL, SensitivityLevel.CONFIDENTIAL)


# ---- Tier determination tests ----------------------------------------------
class TestTierDetermination:
    def test_simple_public_routes_edge(self):
        tier, reason = _determine_tier(
            complexity=ComplexityLevel.SIMPLE,
            sensitivity=SensitivityLevel.PUBLIC,
            intent_confidence=0.95,
            complexity_score=0.2,
        )
        assert tier == InferenceTier.EDGE
        assert "edge" in reason.lower() or "simple" in reason.lower()

    def test_medium_public_routes_cloud(self):
        tier, _ = _determine_tier(
            complexity=ComplexityLevel.MEDIUM,
            sensitivity=SensitivityLevel.PUBLIC,
            intent_confidence=0.90,
            complexity_score=0.55,
        )
        assert tier == InferenceTier.CLOUD

    def test_expert_public_routes_rlm(self):
        tier, _ = _determine_tier(
            complexity=ComplexityLevel.EXPERT,
            sensitivity=SensitivityLevel.PUBLIC,
            intent_confidence=0.92,
            complexity_score=0.92,
        )
        assert tier == InferenceTier.RLM

    def test_restricted_always_local(self):
        """GDPR critical: restricted data must never go to cloud/edge."""
        for complexity in ComplexityLevel:
            tier, reason = _determine_tier(
                complexity=complexity,
                sensitivity=SensitivityLevel.RESTRICTED,
                intent_confidence=0.99,
                complexity_score=0.1,
            )
            assert tier in (InferenceTier.SLM, InferenceTier.RLM), (
                f"Restricted data routed to {tier} for {complexity} — GDPR violation!"
            )

    def test_confidential_always_local(self):
        """Confidential data must not leave the network."""
        tier, _ = _determine_tier(
            complexity=ComplexityLevel.SIMPLE,
            sensitivity=SensitivityLevel.CONFIDENTIAL,
            intent_confidence=0.99,
            complexity_score=0.1,
        )
        assert tier in (InferenceTier.SLM, InferenceTier.RLM)

    def test_low_confidence_escalates_to_cloud(self):
        """When SLM is unsure, escalate to cloud for safety."""
        tier, reason = _determine_tier(
            complexity=ComplexityLevel.SIMPLE,
            sensitivity=SensitivityLevel.PUBLIC,
            intent_confidence=0.60,  # below 0.85 threshold
            complexity_score=0.2,
        )
        assert tier == InferenceTier.CLOUD
        assert "confidence" in reason.lower()
