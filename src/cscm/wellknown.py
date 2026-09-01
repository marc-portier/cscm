# src/cscm/wellknown.py
from cscm.model import LabeledPosition, Swimmer
from cscm.current.current_model import UniformCurrentsModel
import random


# Positions
POSITIONS = dict(
    # WKT,name,description
    # "POINT (2.9704106714146716 51.25743146659003)",Bredene Post 4,
    BREDENE_POST4=LabeledPosition(
        label="Bredene Reddingspost 4",
        lat=51.25743146659003, lon=2.9704106714146716
    ),
    # "POINT (2.9560906 51.2729652)",Bredene Post 4 Proxy,
    BREDENE_POST4_PROXY=LabeledPosition(
        label="Bredene Reddingspost 4 Proxy",
        lat=51.2729652, lon=2.9560906
    ),
    # "POINT (2.62575 51.1194)",Koksijde,
    KOKSIJDE=LabeledPosition(
        label="Koksijde",
        lat=51.11940, lon=2.62575
    ),
    # "POINT (2.6101006 51.1345606)",Koksijde Proxy,
    KOKSIJDE_PROXY=LabeledPosition(
        label="Koksijde Proxy",
        lat=51.1345606, lon=2.6101006
    ),
    # "POINT (2.72333 51.15667)",Nieuwpoort,
    NIEUWPOORT=LabeledPosition(
        label="Nieuwpoort",
        lat=51.15667, lon=2.72333
    ),
    # "POINT (2.707728 51.1711833)",Nieuwpoort Proxy,
    NIEUWPOORT_PROXY=LabeledPosition(
        label="Nieuwpoort Proxy",
        lat=51.1711833, lon=2.707728
    ),
    # "POINT (1.58333 52.08333)",Orford Ness,
    ORFORD_NESS=LabeledPosition(
        label="Orford Ness",
        lat=52.08333, lon=1.58333
    ),
    # "POINT (1.6081401 52.0736728)",Orford Ness Proxy,
    ORFORD_NESS_PROXY=LabeledPosition(
        label="Orford Ness Proxy",
        lat=52.0736728, lon=1.6081401
    ),
    # "POINT (1.4451754 51.3836514)",Kingsgate,
    KINGSGATE=LabeledPosition(
        label="Kingsgate",
        lat=51.3836514, lon=1.4451754
    ),
    # "POINT (1.4707437 51.3914205)",Kingsgate Proxy,
    KINGSGATE_PROXY=LabeledPosition(
        label="Kingsgate Proxy",
        lat=51.3914205, lon=1.4707437
    ),
    # "POINT (1.3060091 51.1132473)",Dover,Shakespeare Beach
    DOVER=LabeledPosition(
        label="Dover, Shakespeare Beach",
        lat=51.1132473, lon=1.3060091
    ),
    # "POINT (1.3204159 51.0976191)",Dover Proxy,
    DOVER_PROXY=LabeledPosition(
        label="Dover Proxy",
        lat=51.0976191, lon=1.3204159
    ),
    # "POINT (1.6962061 50.9202391)",Cap Blanc Nez,
    CAP_BLANC_NEZ=LabeledPosition(
        label="Cap Blanc Nez",
        lat=50.9202391, lon=1.6962061
    ),
    # "POINT (1.6716473 50.9298626)",Cap Blanc Nez Proxy,
    CAP_BLANC_NEZ_PROXY=LabeledPosition(
        label="Cap Blanc Nez Proxy",
        lat=50.9298626, lon=1.6716473
    ),
    # "POINT (1.5585258 50.9823472)",W 1/3,
    W_1_3=LabeledPosition(
        label="W 1/3",
        lat=50.9823472, lon=1.5585258
    ),
    # "POINT (1.4459964 51.0374139)",W 2/3,
    W_2_3=LabeledPosition(
        label="W 2/3",
        lat=51.0374139, lon=1.4459964
    ),
    # "POINT (1.5028793 51.0096289)",W 1/2,
    W_1_2=LabeledPosition(
        label="W 1/2",
        lat=51.0096289, lon=1.5028793
    ),
    # "POINT (1.857809 51.3099446)",M 2/3,
    M_2_3=LabeledPosition(
        label="M 2/3",
        lat=51.3099446, lon=1.857809
    ),
    # "POINT (2.2672317 51.2410691)",M 1/3,
    M_1_3=LabeledPosition(
        label="M 1/3",
        lat=51.2410691, lon=2.2672317
    ),
    # "POINT (2.0602783 51.2749006)",M 1/2,
    M_1_2=LabeledPosition(
        label="M 1/2",
        lat=51.2749006, lon=2.0602783
    ),
    # "POINT (1.6391558 51.3486548)",M 5/6,
    M_5_6=LabeledPosition(
        label="M 5/6",
        lat=51.3486548, lon=1.6391558
    ),
    # "POINT (2.4790661 51.200747)",M 1/6,
    M_1_6=LabeledPosition(
        label="M 1/6",
        lat=51.200747, lon=2.4790661
    ),
    # "POINT (2.1533663 51.6252596)",E 1/2,
    E_1_2=LabeledPosition(
        label="E 1/2",
        lat=51.6252596, lon=2.1533663
    ),
    # "POINT (1.7656382 51.9317262)",E 5/6,
    E_5_6=LabeledPosition(
        label="E 5/6",
        lat=51.9317262, lon=1.7656382
    ),
    # "POINT (1.9593153 51.7792136)",E 2/3,
    E_2_3=LabeledPosition(
        label="E 2/3",
        lat=51.7792136, lon=1.9593153
    ),
    # "POINT (2.3450114 51.4696367)",E 1/3,
    E_1_3=LabeledPosition(
        label="E 1/3",
        lat=51.4696367, lon=2.3450114
    ),
    # "POINT (2.5389216 51.3109382)",E 1/6,
    E_1_6=LabeledPosition(
        label="E 1/6",
        lat=51.3109382, lon=2.5389216
    ),
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
    BCH_UNIFORM=UniformCurrentsModel(),
)
