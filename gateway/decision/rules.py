from gateway.decision.decision import Decision

def evaluate_rules(features: dict) -> Decision:
    """
    Deterministic rule-based decision engine.
    Input: feature dictionary from Phase 5.3
    Output: Decision enum
    """

    # Guard rail — missing or empty features
    if not features:
        return Decision.ALLOW

    total_requests = features.get("total_requests", 0)
    requests_per_second = features.get("requests_per_second", 0.0)
    blocked_ratio = features.get("blocked_ratio", 0.0)
    throttled_ratio = features.get("throttled_ratio", 0.0)
    unique_endpoints = features.get("unique_endpoints", 0)
    entropy = features.get("endpoints_entropy", 0.0)

    # 🔴 Rule 1 — Repeated abuse → BLOCK
    if blocked_ratio >= 0.6 and total_requests >= 5:
        return Decision.BLOCK

    # 🟠 Rule 2 — Sustained high traffic → THROTTLE
    if requests_per_second > 5:
        return Decision.THROTTLE

    # 🟠 Rule 3 — Endpoint scanning behavior → THROTTLE
    if unique_endpoints >= 10 and entropy >= 2.5:
        return Decision.THROTTLE

    # 🟢 Default — Safe behavior
    return Decision.ALLOW
