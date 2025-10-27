"""Form baseline predictor module.

Predicts expected form metrics (GCT, VO, VR) from pace using trained models.
"""

from .trainer import GCTPowerModel, LinearModel


def predict_expectations(
    models: dict[str, GCTPowerModel | LinearModel],
    pace_s_per_km: float,
) -> dict[str, float]:
    """Predict expected form metrics from pace.

    Args:
        models: Dictionary of trained models with keys:
            - 'gct': GCTPowerModel for ground contact time
            - 'vo': LinearModel for vertical oscillation
            - 'vr': LinearModel for vertical ratio
        pace_s_per_km: Pace in seconds per kilometer

    Returns:
        Dictionary containing:
            - pace: Input pace (sec/km)
            - speed_mps: Speed in meters per second
            - gct_ms_exp: Expected ground contact time (ms)
            - vo_cm_exp: Expected vertical oscillation (cm)
            - vr_pct_exp: Expected vertical ratio (%)

    Example:
        >>> from tools.form_baseline.trainer import train_models
        >>> models = train_models(training_data)
        >>> expectations = predict_expectations(models, pace_s_per_km=240.0)
        >>> print(expectations['gct_ms_exp'])  # Expected GCT at 4:00/km pace
        210.5
    """
    # Convert pace to speed (m/s)
    speed_mps = 1000.0 / pace_s_per_km

    # Predict expected values using models
    # Type assertion: we know gct is GCTPowerModel, vo/vr are LinearModel
    gct_model = models["gct"]
    assert isinstance(gct_model, GCTPowerModel)
    gct_ms_exp = gct_model.predict_inverse(speed_mps)

    vo_model = models["vo"]
    assert isinstance(vo_model, LinearModel)
    vo_cm_exp = vo_model.predict(speed_mps)

    vr_model = models["vr"]
    assert isinstance(vr_model, LinearModel)
    vr_pct_exp = vr_model.predict(speed_mps)

    return {
        "pace": pace_s_per_km,
        "speed_mps": speed_mps,
        "gct_ms_exp": gct_ms_exp,
        "vo_cm_exp": vo_cm_exp,
        "vr_pct_exp": vr_pct_exp,
    }
