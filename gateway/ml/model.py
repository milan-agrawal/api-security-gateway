import numpy as np
from sklearn.ensemble import IsolationForest

model = IsolationForest(
    n_estimators=100,
    contamination=0.05,
    random_state=42
)

# Minimal baseline (normal behavior)
baseline = np.array([
    [10, 1, 0.002, 0.1, 0.0, 0.0, 0.0],
    [12, 1, 0.003, 0.12, 0.0, 0.0, 0.0],
    [8,  1, 0.001, 0.08, 0.0, 0.0, 0.0],
])

model.fit(baseline)
