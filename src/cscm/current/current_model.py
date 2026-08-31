# src/cscm/current/current_model.py

from cscm.model import CurrentsModel, Position, SpeedVector, TimePhaseCalibration
from datetime import datetime


class UniformCurrentsModel(CurrentsModel):
    # just have a fixed direction
    # assume some max speed
    # have that speed follow the sine according to the tide and put the speed amplitude in lunar envelope

    def __init__(self, *,
                 direction_deg: float = 55.0,
                 v_peak_mps: float = 3.4,
                 tide_period_s: int = 6.21 * 60 * 60,
                 lunar_period_s: int = 57 * 6.21 * 60 * 60,
                 lunar_factor: float = 0.8,
    ):
        # TODO: implement the uniform currents model with the given parameters
        ...

    def get_current(self, position: Position, moment: datetime) -> SpeedVector:
        # TODO: implement the method to return the current speed vector at the given position and moment
        SpeedVector(0, 0)

    def has_absolute_time_reference(self) -> bool:
        return False

    def calibrate_time_phase(self, tpc: TimePhaseCalibration) -> TimePhaseCalibration:
        # TODO - do actually somethign useful in the calibration, but for now just return the input
        return tpc


class TriangularCurrentsModel(CurrentsModel):
    # direct to a certain point
    # recalibrate speed based on distance from the point
    # have that speed follow the sine according to the tide and put the speed amplitude in lunar envelope 
    # will have to play around to get this actually useful
    pass


class CmemsActualsCurrentModel(CurrentsModel):
    # point to a file, get associated metadata precalculated (or produce on the spot)
    # actual models will have a limited time-range in them
    pass


class CmemsAverageCurrentsModel(CurrentsModel):
    # point to a file, get associated metadata precalculated (or produce on the spot)
    # average models will not have an idea of absolute time
    pass
