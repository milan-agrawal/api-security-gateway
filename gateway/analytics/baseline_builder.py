"""
Phase 5.5 - Baseline Dataset Builder

This module creates a baseline dataset from historical "clean" API traffic.
It analyzes only ALLOW decisions to understand normal behavior patterns.

Purpose:
- Extract clean traffic windows from historical data
- Generate feature vectors for ML training
- Create baseline dataset for anomaly detection

Safety:
- Read-only database operations
- No live system impact
- Offline analysis only
"""

from sqlalchemy.orm import Session
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

from gateway.models import SecurityEvent
from gateway.analytics.feature_extractor import extract_features

# Configuration constants
WINDOW_SECONDS = 60  # 60-second windows for analysis
MIN_REQUESTS_PER_WINDOW = 5  # Minimum activity to avoid noise


def collect_baseline_windows(db: Session) -> Dict[Tuple[str, int], List[SecurityEvent]]:
    """
    Collects clean baseline windows from historical traffic.
    
    Only includes:
    - ALLOW decisions (clean traffic)
    - Grouped by API key and time window
    - Chronologically ordered
    
    Args:
        db: Database session for read-only access
        
    Returns:
        Dictionary mapping (api_key, window_id) to list of events
        
    Example:
        {
            ('secret123', 1641024000): [SecurityEvent1, SecurityEvent2, ...],
            ('secret123', 1641024060): [SecurityEvent3, SecurityEvent4, ...],
        }
    """
    
    print("Collecting baseline windows from historical data...")
    
    # Query only clean traffic (ALLOW decisions)
    events = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.decision == "ALLOW")
        .order_by(SecurityEvent.timestamp.asc())
        .all()
    )
    
    print(f"Found {len(events)} ALLOW events in database")
    
    # Group events into time windows
    windows = defaultdict(list)
    
    for event in events:
        # Convert timestamp to window ID (60-second buckets)
        window_start = int(event.timestamp.timestamp()) // WINDOW_SECONDS
        key = (event.api_key, window_start)
        windows[key].append(event)
    
    print(f"Organized into {len(windows)} time windows")
    
    return dict(windows)


def build_baseline_dataset(db: Session) -> List[Dict[str, Any]]:
    """
    Builds baseline dataset from clean traffic windows.
    
    Process:
    1. Collect clean traffic windows
    2. Filter out sparse windows (< MIN_REQUESTS_PER_WINDOW)
    3. Extract features using existing feature_extractor
    4. Return list of feature dictionaries
    
    Args:
        db: Database session for read-only access
        
    Returns:
        List of feature dictionaries representing normal behavior
        
    Example:
        [
            {
                'total_requests': 12,
                'unique_endpoints': 1, 
                'requests_per_second': 0.2,
                'endpoints_entropy': 0.0,
                'blocked_ratio': 0.0,
                'throttled_ratio': 0.0,
                # ... more features
            },
            # ... more windows
        ]
    """
    
    print("Building baseline dataset...")
    
    # Step 1: Collect baseline windows
    windows = collect_baseline_windows(db)
    
    # Step 2: Extract features from each window
    dataset = []
    sparse_windows = 0
    
    for (api_key, window_id), events in windows.items():
        # Skip sparse windows to avoid noise
        if len(events) < MIN_REQUESTS_PER_WINDOW:
            sparse_windows += 1
            continue
        
        # Extract behavioral features using existing logic
        features = extract_features(events)
        
        # Skip if feature extraction failed
        if not features:
            continue
        
        # Add metadata for analysis
        features['api_key'] = api_key
        features['window_id'] = window_id
        features['window_events'] = len(events)
        features['window_start'] = datetime.fromtimestamp(window_id * WINDOW_SECONDS)
        
        dataset.append(features)
    
    print(f"Created baseline dataset:")
    print(f"   - {len(dataset)} feature vectors")
    print(f"   - {sparse_windows} sparse windows filtered out")
    print(f"   - Minimum {MIN_REQUESTS_PER_WINDOW} requests per window")
    
    return dataset


def analyze_baseline_distribution(dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes the statistical distribution of baseline features.
    
    Useful for:
    - Understanding normal behavior ranges
    - Setting anomaly detection thresholds
    - Data quality assessment
    
    Args:
        dataset: List of feature dictionaries from build_baseline_dataset()
        
    Returns:
        Statistical summary of baseline features
    """
    
    if not dataset:
        return {"error": "Empty dataset"}
    
    print("Analyzing baseline feature distribution...")
    
    # Extract numeric features
    numeric_features = {}
    for feature_dict in dataset:
        for key, value in feature_dict.items():
            if isinstance(value, (int, float)) and key not in ['window_id']:
                if key not in numeric_features:
                    numeric_features[key] = []
                numeric_features[key].append(value)
    
    # Calculate statistics
    stats = {}
    for feature, values in numeric_features.items():
        if values:
            stats[feature] = {
                'count': len(values),
                'min': min(values),
                'max': max(values),
                'mean': sum(values) / len(values),
                'median': sorted(values)[len(values) // 2]
            }
    
    # Overall dataset info
    api_keys = set(d.get('api_key') for d in dataset)
    
    summary = {
        'total_windows': len(dataset),
        'unique_api_keys': len(api_keys),
        'api_keys': list(api_keys),
        'feature_statistics': stats,
        'sample_window': dataset[0] if dataset else None
    }
    
    print(f"Analysis complete: {len(dataset)} windows from {len(api_keys)} API keys")
    
    return summary


def export_baseline_dataset(dataset: List[Dict[str, Any]], filename: str = "baseline_dataset.json") -> str:
    """
    Exports baseline dataset to JSON file for external analysis.
    
    Args:
        dataset: Baseline dataset from build_baseline_dataset()
        filename: Output filename (default: baseline_dataset.json)
        
    Returns:
        Path to exported file
    """
    import json
    from datetime import datetime
    
    # Convert datetime objects to strings for JSON serialization
    exportable_dataset = []
    for item in dataset:
        exportable_item = {}
        for key, value in item.items():
            if isinstance(value, datetime):
                exportable_item[key] = value.isoformat()
            else:
                exportable_item[key] = value
        exportable_dataset.append(exportable_item)
    
    # Export with metadata
    export_data = {
        'metadata': {
            'export_timestamp': datetime.now().isoformat(),
            'phase': '5.5',
            'description': 'Baseline dataset from clean API traffic',
            'window_seconds': WINDOW_SECONDS,
            'min_requests_per_window': MIN_REQUESTS_PER_WINDOW,
            'total_windows': len(exportable_dataset)
        },
        'dataset': exportable_dataset
    }
    
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"Exported {len(exportable_dataset)} baseline windows to {filename}")
    return filename