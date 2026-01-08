from gateway.decision.decision import Decision
from gateway.ml.labels import MLLabel

def correlate_decisions(
    rule_decision: Decision,
    ml_label: MLLabel | None
) -> dict:
    """
    Correlates rule-based decision with ML signal.
    This function NEVER changes enforcement.
    """

    # ML unavailable or disabled
    if ml_label is None:
        return {
            "agreement": "UNKNOWN",
            "confidence": "RULE_ONLY",
            "summary": "ML unavailable"
        }

    # Strong agreement cases
    if rule_decision == Decision.BLOCK and ml_label == MLLabel.ANOMALOUS:
        return {
            "agreement": "STRONG",
            "confidence": "HIGH",
            "summary": "Rules and ML agree on malicious behavior"
        }

    if rule_decision == Decision.ALLOW and ml_label == MLLabel.NORMAL:
        return {
            "agreement": "STRONG",
            "confidence": "HIGH",
            "summary": "Rules and ML agree on normal behavior"
        }

    # Partial agreement
    if rule_decision == Decision.THROTTLE and ml_label in (
        MLLabel.SUSPICIOUS,
        MLLabel.ANOMALOUS
    ):
        return {
            "agreement": "PARTIAL",
            "confidence": "MEDIUM",
            "summary": "ML supports cautious rule action"
        }

    # Disagreement cases
    if rule_decision == Decision.ALLOW and ml_label == MLLabel.ANOMALOUS:
        return {
            "agreement": "DISAGREE",
            "confidence": "LOW",
            "summary": "ML flags anomaly but rules allow"
        }

    if rule_decision == Decision.BLOCK and ml_label == MLLabel.NORMAL:
        return {
            "agreement": "DISAGREE",
            "confidence": "LOW",
            "summary": "Rules block but ML sees normal behavior"
        }

    # Default fallback
    return {
        "agreement": "NEUTRAL",
        "confidence": "RULE_PRIORITY",
        "summary": "Rules take precedence"
    }