import numpy as np
from gateway.ml.labels import MLLabel
from gateway.ml.model import model, is_model_ready

def infer_ml_signal(feature_vector: list[float]) -> dict:
    """
    Read-only ML inference.
    Never blocks, throttles, or alters flow.
    """

    # Guard rail — model not trained yet
    if not is_model_ready():
        return {
            "score": None,
            "label": MLLabel.NORMAL
        }

    X = np.array([feature_vector])

    score = model.decision_function(X)[0]

    if score < -0.4:
        label = MLLabel.ANOMALOUS
    elif score < -0.2:
        label = MLLabel.SUSPICIOUS
    else:
        label = MLLabel.NORMAL

    return {
        "score": round(float(score), 4),
        "label": label
    }