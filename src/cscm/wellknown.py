# src/cscm/wellknown.py
from .model import LabeledPosition, Swimmer
from .current import UniformCurrentsModel, TriangularCurrentsModel, CmemsActualsCurrentModel, CmemsAverageCurrentsModel
import random


# Positions
POSITIONS = dict(
    NIEUWPOORT=LabeledPosition(
        label="Nieuwpoort",
        lat=51.15667, lon=2.72333),
    KOKSIJDE=LabeledPosition(
        label="Koksijde",
        lat=51.11940, lon=2.62575),
    KOKSIJDE_END_316_HT=LabeledPosition(
        label="From Koksijde (projected end of swim 316° at HT)",
        lat=51.264652, lon=2.402563),
    KOKSIJDE_END_333_LT=LabeledPosition(
        label="From Koksijde (projected end of swim 333° at LT)",
        lat=51.298858, lon=2.479862),
    ORFORD=LabeledPosition(
        label="Orford Ness",
        lat=52.08333, lon=1.58333),
    KINGSGATE=LabeledPosition(
        label="Kingsgate Bay",
        lat=51.38333, lon=1.44333),
    DOVER=LabeledPosition(
        label="Shakespeare Beach, Dover",
        lat=51.1130669, lon=1.2998859),
    CAPGRISNEZ=LabeledPosition(
        label="Cap Gris-Nez, Frankrijk",
        lat=50.925668, lon=1.706695),
)


def constant(value: float):
    """
    Returns a function that always returns the same value.
    """
    return lambda time_s: value


def random_jitter(percentage: float, base: float = None, max: float = None):
    """
    Returns a function that returns a random jittered value based on the given percentage.
    The jittered value is calculated as: value * (1 + random.uniform(-percentage, percentage))
    If max is provided, the jittered value will be capped at max.
    """
    def jitter_fn(time_s: int, value: float):
        if base is not None:
            value = base
        jittered_value = value * (1 + random.uniform(-percentage, percentage))
        if max is not None:
            return min(jittered_value, max)
        return jittered_value

    return jitter_fn


# Swimmers
SWIMMERS = dict(
    MBL_MIDR=Swimmer(
        name="Marieke Blomme",
        speed_fn=constant(1.0),    # 1mps constant speed, aka 3.6 km/h
        speed_jitter_fn=None,
        heading_jitter_fn=None,
    ),
    MBL_EXTR=Swimmer(
        name="Marieke Blomme",
        speed_fn=constant(0.833),  # 3.0 km/h average on longer distances, slow starting for endurance
        speed_jitter_fn=None,
        heading_jitter_fn=None,
    ),
    MPO=Swimmer(
        name="Marc Portier",
        speed_fn=constant(0.91),
        speed_jitter_fn=random_jitter(0.05, max=0.3),    # 5% jitter, max 0.3 m/s
        heading_jitter_fn=random_jitter(1.0, base=2.0)   # +/- 2 degree jitter),
    ),
)


# Current Models
CURRENT_MODELS = dict(
    BCH_UNIFORM=UniformCurrentsModel(
        v_peak_mps=3.8,
        tide_period_s=6.21 * 60 * 60,
        tide_factor=1,
        lunar_period_s=28 * 6.21 * 60 * 60,
        lunar_factor=0.8,
    ),
)
