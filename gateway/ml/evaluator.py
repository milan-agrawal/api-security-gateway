"""
Phase 5.6 - ML Threshold Calibration & Evaluation

This module calibrates ML detection thresholds using baseline data.
It provides data-driven threshold recommendations for normal vs suspicious behavior.

Purpose:
- Analyze ML score distributions on clean baseline traffic
- Recommend scientifically-justified thresholds
- Validate ML behavior against known-good data
- Ensure no false positives on legitimate traffic

Safety:
- Read-only analysis operations
- No live system behavior changes
- Advisory recommendations only
"""

import numpy as np
from typing import Dict, List, Tuple, Any
from gateway.ml.model import model
from gateway.analytics.baseline_builder import build_baseline_dataset


def prepare_feature_matrix(baseline_dataset: List[Dict[str, Any]]) -> np.ndarray:
    """
    Converts baseline dataset to ML-ready feature matrix.
    
    Args:
        baseline_dataset: List of feature dictionaries from baseline_builder
        
    Returns:
        NumPy array ready for ML model input
        
    Note:
        This must match the feature order expected by your ML model
    """
    
    print(f"Preparing feature matrix from {len(baseline_dataset)} baseline windows...")
    
    # Extract features in the order expected by the ML model
    feature_vectors = []
    
    for window_features in baseline_dataset:
        # Convert feature dict to ordered array (matches ML model expectations)
        feature_vector = [
            window_features.get('total_requests', 0),
            window_features.get('requests_per_second', 0.0),
            window_features.get('blocked_ratio', 0.0),
            window_features.get('endpoints_entropy', 0.0),
            window_features.get('throttled_ratio', 0.0),
            window_features.get('inter_arrivals_variance', 0.0),
            0.0  # placeholder for additional features
        ]
        feature_vectors.append(feature_vector)
    
    X = np.array(feature_vectors)
    print(f"Feature matrix shape: {X.shape}")
    
    return X


def evaluate_baseline_scores(baseline_dataset: List[Dict[str, Any]]) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Evaluates ML score distribution on baseline traffic.
    
    This is the core Phase 5.6.1 function that analyzes how your ML model
    scores known-good traffic to establish normal behavior ranges.
    
    Args:
        baseline_dataset: Clean baseline data from Phase 5.5
        
    Returns:
        Tuple of (raw_scores, statistics_dict)
        
    Example output:
        scores: array([-0.12, -0.08, -0.15, ...])
        stats: {
            'min': -0.42,
            'max': 0.15, 
            'mean': -0.02,
            'std': 0.05,
            'p95': -0.18,
            'p99': -0.25
        }
    """
    
    print("Starting ML score evaluation on baseline data...")
    
    if not baseline_dataset:
        raise ValueError("Empty baseline dataset - run Phase 5.5 first")
    
    # Convert to ML feature matrix
    X = prepare_feature_matrix(baseline_dataset)
    
    # Get ML scores for baseline (known-good) data
    print("Computing ML scores for baseline windows...")
    scores = model.decision_function(X)
    
    # Calculate statistical distribution
    stats = {
        "count": len(scores),
        "min": float(np.min(scores)),
        "max": float(np.max(scores)),
        "mean": float(np.mean(scores)),
        "std": float(np.std(scores)),
        "median": float(np.median(scores)),
        
        # Percentiles (key for threshold setting)
        "p95": float(np.percentile(scores, 5)),   # 95% of normal traffic above this
        "p99": float(np.percentile(scores, 1)),   # 99% of normal traffic above this
        "p99_9": float(np.percentile(scores, 0.1)), # 99.9% of normal traffic above this
        
        # Upper percentiles (for reference)
        "p75": float(np.percentile(scores, 25)),
        "p90": float(np.percentile(scores, 10)),
    }
    
    print(f"Baseline score analysis complete:")
    print(f"  Score range: {stats['min']:.3f} to {stats['max']:.3f}")
    print(f"  Mean ± std: {stats['mean']:.3f} ± {stats['std']:.3f}")
    print(f"  95th percentile: {stats['p95']:.3f}")
    print(f"  99th percentile: {stats['p99']:.3f}")
    
    return scores, stats


def recommend_thresholds(score_stats: Dict[str, float]) -> Dict[str, float]:
    """
    Recommends ML thresholds based on baseline score distribution.
    
    Uses statistical analysis to suggest where to draw lines between
    NORMAL, SUSPICIOUS, and ANOMALOUS behavior.
    
    Args:
        score_stats: Statistics from evaluate_baseline_scores()
        
    Returns:
        Dictionary with recommended threshold values
        
    Methodology:
        - NORMAL threshold: 95th percentile (captures 95% of normal traffic)
        - SUSPICIOUS threshold: 99th percentile (captures 99% of normal traffic)
        - Anything below SUSPICIOUS = ANOMALOUS
    """
    
    print("Calculating data-driven threshold recommendations...")
    
    # Conservative approach: Use percentiles to minimize false positives
    thresholds = {
        "NORMAL_THRESHOLD": score_stats["p95"],      # 95% of baseline above this
        "SUSPICIOUS_THRESHOLD": score_stats["p99"],   # 99% of baseline above this
        "ANOMALOUS_THRESHOLD": score_stats["p99_9"],  # 99.9% of baseline above this
    }
    
    # Add interpretation ranges
    thresholds.update({
        "NORMAL_RANGE": f"score >= {thresholds['NORMAL_THRESHOLD']:.3f}",
        "SUSPICIOUS_RANGE": f"{thresholds['SUSPICIOUS_THRESHOLD']:.3f} <= score < {thresholds['NORMAL_THRESHOLD']:.3f}",
        "ANOMALOUS_RANGE": f"score < {thresholds['SUSPICIOUS_THRESHOLD']:.3f}",
    })
    
    print(f"Recommended thresholds (data-driven):")
    print(f"  NORMAL: >= {thresholds['NORMAL_THRESHOLD']:.3f}")
    print(f"  SUSPICIOUS: {thresholds['SUSPICIOUS_THRESHOLD']:.3f} to {thresholds['NORMAL_THRESHOLD']:.3f}")
    print(f"  ANOMALOUS: < {thresholds['SUSPICIOUS_THRESHOLD']:.3f}")
    
    return thresholds


def validate_thresholds(baseline_dataset: List[Dict[str, Any]], thresholds: Dict[str, float]) -> Dict[str, Any]:
    """
    Validates recommended thresholds against baseline data.
    
    Ensures that thresholds make sense and won't cause false positives
    on known-good traffic.
    
    Args:
        baseline_dataset: Clean baseline data
        thresholds: Recommended thresholds from recommend_thresholds()
        
    Returns:
        Validation report with false positive rates and recommendations
    """
    
    print("Validating thresholds against baseline data...")
    
    # Get scores for validation
    X = prepare_feature_matrix(baseline_dataset)
    scores = model.decision_function(X)
    
    # Count classifications
    normal_count = np.sum(scores >= thresholds["NORMAL_THRESHOLD"])
    suspicious_count = np.sum((scores >= thresholds["SUSPICIOUS_THRESHOLD"]) & 
                            (scores < thresholds["NORMAL_THRESHOLD"]))
    anomalous_count = np.sum(scores < thresholds["SUSPICIOUS_THRESHOLD"])
    
    total_count = len(scores)
    
    # Calculate rates
    validation_report = {
        "total_baseline_windows": total_count,
        "normal_count": int(normal_count),
        "suspicious_count": int(suspicious_count), 
        "anomalous_count": int(anomalous_count),
        
        "normal_rate": float(normal_count / total_count),
        "suspicious_rate": float(suspicious_count / total_count),
        "anomalous_rate": float(anomalous_count / total_count),
        
        # Key validation metrics
        "false_positive_rate": float(anomalous_count / total_count),  # Should be very low
        "threshold_quality": "GOOD" if (anomalous_count / total_count) < 0.05 else "NEEDS_ADJUSTMENT"
    }
    
    print(f"Threshold validation results:")
    print(f"  Normal: {validation_report['normal_count']} ({validation_report['normal_rate']:.1%})")
    print(f"  Suspicious: {validation_report['suspicious_count']} ({validation_report['suspicious_rate']:.1%})")
    print(f"  Anomalous: {validation_report['anomalous_count']} ({validation_report['anomalous_rate']:.1%})")
    print(f"  False positive rate: {validation_report['false_positive_rate']:.1%}")
    print(f"  Threshold quality: {validation_report['threshold_quality']}")
    
    return validation_report


def run_complete_evaluation(db_session) -> Dict[str, Any]:
    """
    Runs complete Phase 5.6 evaluation pipeline.
    
    This is the main function that orchestrates all Phase 5.6 steps:
    1. Load baseline data (Phase 5.5)
    2. Evaluate ML score distribution 
    3. Recommend thresholds
    4. Validate thresholds
    
    Args:
        db_session: Database session for baseline data access
        
    Returns:
        Complete evaluation report with scores, thresholds, and validation
    """
    
    print("=" * 50)
    print("PHASE 5.6 - ML THRESHOLD CALIBRATION")
    print("=" * 50)
    
    # Step 1: Load baseline dataset from Phase 5.5
    print("\nStep 1: Loading baseline dataset...")
    baseline_dataset = build_baseline_dataset(db_session)
    
    if not baseline_dataset:
        raise ValueError("No baseline data found. Run Phase 5.5 first to create baseline dataset.")
    
    # Step 2: Evaluate score distribution
    print("\nStep 2: Evaluating ML score distribution...")
    scores, stats = evaluate_baseline_scores(baseline_dataset)
    
    # Step 3: Recommend thresholds
    print("\nStep 3: Calculating data-driven thresholds...")
    thresholds = recommend_thresholds(stats)
    
    # Step 4: Validate thresholds
    print("\nStep 4: Validating threshold recommendations...")
    validation = validate_thresholds(baseline_dataset, thresholds)
    
    # Compile complete report
    evaluation_report = {
        "phase": "5.6",
        "description": "ML Threshold Calibration & Evaluation",
        "baseline_windows": len(baseline_dataset),
        "score_statistics": stats,
        "recommended_thresholds": thresholds,
        "validation_results": validation,
        "status": "COMPLETE" if validation["threshold_quality"] == "GOOD" else "NEEDS_REVIEW"
    }
    
    print(f"\nPhase 5.6 Status: {evaluation_report['status']}")
    print("=" * 50)
    
    return evaluation_report