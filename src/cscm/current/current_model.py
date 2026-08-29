# src/cscm/current/current_model.py

from cscm.model import CurrentsModel


class UniformCurrentsModel(CurrentsModel):
    # just have a fixed direction
    # assume some max speed
    # have that speed follow the sine according to the tide and put the speed amplitude in lunar envelope 
    pass


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
