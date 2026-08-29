# src/cscm/model.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Callable
import pandas as pd


@dataclass
class SpeedVector:
    """
    Class representing a 2D vector of movement in meters per second (m/s)
    Attributes:
        v_east_mps (float): The change in the x-direction (longitude).
        v_north_mps (float): The change in the y-direction (latitude).
    """
    v_east_mps: float
    v_north_mps: float

    @property
    def speed_mps(self) -> float:
        """
        Calculate the magnitude of the speed vector.

        :return: The magnitude of the speed vector.
        """
        return math.sqrt(self.v_east_mps ** 2 + self.v_north_mps ** 2)

    @property
    def direction_rad(self) -> float:
        """
        Calculate the direction of the speed vector in radians.

        :return: The direction of the speed vector in radians versus North (0 rad) and East (pi/2 rad).
        """
        return math.atan2(self.v_east_mps, self.v_north_mps)

    @property
    def direction_deg(self) -> float:
        """
        Calculate the direction of the speed vector in degrees.

        :return: The direction of the speed vector in degrees versus North (0 deg) and East (90 deg).
        """
        return math.degrees(self.direction_rad)


@dataclass
class Position:
    """
    Class representing a 2D position.
    uses WGS84 coordinates (EPSG:4326).

    Attributes:
        lat (float): The latitude of the position.
        lon (float): The longitude of the position.
    """
    lat: float
    lon: float

    def relative_speed_time(self, speed: SpeedVector, time_s: float) -> 'Position':
        """
        Calculate the new position after moving with a given speed vector for a specified time.

        :param speed_vector: The speed vector representing movement in meters per second.
        :param time_s: The time in seconds for which the movement occurs.
        :return: A new Position object representing the new position.
        """
        # Convert speed from m/s to degrees of latitude and longitude
        delta_lat = speed.v_north_mps * time_s / 111132  # Approximate conversion factor for latitude
        delta_lon = speed.v_east_mps * time_s / (111132 * math.cos(math.radians(self.lat)))  # Adjust for longitude

        return Position(lat=self.lat + delta_lat, lon=self.lon + delta_lon)


@dataclass
class LabeledPosition(Position):
    """
    Class representing a 2D position with an associated label.
    uses WGS84 coordinates (EPSG:4326).
    """
    label: str


class Environment(ABC):
    """
    Abstract base class for environment parmeters
    """

    @abstractmethod
    @property
    def current(self) -> SpeedVector:
        """
        Gets the current vector of the current.
        """
    pass


class MovingObject(ABC):
    """
    Abstract base class describing behaviour of a moving object in an environment.
    """

    def reset(self, at: Position = None):
        """
        Resets the internal state of the moving object.
        """
        self.time_s: int = 0
        self.pos: Position = at
        self.trajectory: list[(int, Position)] = []  # list of tuples (time_s, Position)
        self.guidance: list[(int, float)] = []  # list of tuples (time_s, heading_deg)

    def start(self, at: Position, environment: Environment):
        """
        Sets starting point for the move. Should reset all internal state of the object to the starting point.
        Can use the instance of the environment to check for model compatibility, should raise an exception (ValueError) if not.
        All subsequent calls to move() are expected to receive smilar Environment instances, but this is not enforced.
        """
        self.reset(at=at.pos)
        if (environment is not None):
            self.env_compat_check(environment)

    @abstractmethod
    def env_compat_check(self, environment: Environment):
        """
        Checks if the environment is compatible with the moving object.
        Should raise an exception (ValueError) if not.
        """
        pass

    def move(self, heading_deg: float, time_s: int, environment: Environment) -> Position:
        """
        Moves the object in the environment for a given time in seconds, with a given intended heading in degrees.
        Note the environment may affect the actual movement (direction and speed) of the object, e.g. by currents.
        Returns the effective new position of the object after the move.
        Should increase the internal lapsed time of the object by the given time, allowing it to keep track of its state and its effect in subsequent moves.
        """
        my_speed_vector = self.calculate_speed(heading_deg, time_s, environment)
        current_vector = environment.get_current()
        effective_speed_vector = SpeedVector(
            v_east_mps=my_speed_vector.v_east_mps + current_vector.v_east_mps,
            v_north_mps=my_speed_vector.v_north_mps + current_vector.v_north_mps,
        )
        # Calculate new position based on effective speed vector and time
        new_lat = self.pos.lat + self.converter.dist_m2lat_diff(effective_speed_vector.v_north_mps * time_s)
        new_lon = self.pos.lon + self.converter.dist_m2lon_diff(effective_speed_vector.v_east_mps * time_s)
        new_position = Position(lat=new_lat, lon=new_lon)
        self.time_s += time_s
        self.pos = new_position
        self.trajectory.append((self.time_s, new_position))
        self.guidance.append((self.time_s, heading_deg))

    def calculate_speed(self, heading_deg: float, time_s: int, environment: Environment) -> SpeedVector:
        """
        Calculates the effective speed vector of the object in the environment for a given time in seconds, with a given intended heading in degrees.
        Note the environment may affect the actual movement (direction and speed) of the object, e.g. by currents.
        Returns the effective speed vector of the object in meters per second.
        """
        proper_speed_mps = self.calculate_proper_speed_mps(heading_deg, time_s, environment)
        proper_direction_deg = heading_deg + self.calculate_proper_direction_deviation(heading_deg, time_s, environment)
        # Convert direction to radians
        proper_direction_rad = math.radians(proper_direction_deg)
        # Calculate speed vector components
        v_east = proper_speed_mps * math.cos(proper_direction_rad)
        v_north = proper_speed_mps * math.sin(proper_direction_rad)
        return SpeedVector(v_east=v_east, v_north=v_north)

    @abstractmethod
    def calculate_proper_speed_mps(self, heading_deg: float, time_s: int, environment: Environment) -> float:
        """
        Calculates the intrinsic speed of the object averaged over the give time_s in seconds.
        This should take into account the internal state (like time_lapsed indicating fatigue, etc.).
        It can use the angle between heading and direction of the current to account for efficiency of movement.
        It can take into effect other conditions in the environment (if available)
        It should however not account for the factual displayment caused by the environment (like current), as this is done in the move() method.
        Returns the effective and intrinisic/proper (no currents!) speed (in meter per second) the object will average during this move.
        """
        pass

    @abstractmethod
    def calculate_proper_direction_deviation(self, heading_deg: float, time_s: int, environment: Environment) -> float:
        """
        Calculates the intrinsic variation on the direction of the object averaged over the given time_s in seconds.
        It should probably just be mainly based on some (minor) random variation, but can be influenced in subtle ways:
        - The internal state (like time_lapsed indicating fatigue, etc.) might affect the ability to maintain a straight course.
        - It can use the angle between heading and direction of the current to account for some tendency to "lean into" the current.
        - It can take into effect other conditions in the environment like waves or wind (if available)
        """
        pass

    # TODO unsure - do we need a clone to fan out simulations from a given state?


class Swimmer(MovingObject):
    """
    Class representing a swimmer, inheriting from MovingObject.
    """

    def __init__(self, name: str, speed_fn, speed_jitter_fn=None, heading_jitter_fn=None):
        """
        Initialize the Swimmer with its name and behavioural functions
        """
        super().__init__()
        self.name = name
        self.speed_fn = speed_fn
        self.speed_jitter_fn = speed_jitter_fn
        self.heading_jitter_fn = heading_jitter_fn

    def calculate_proper_speed_mps(self, heading_deg: float, time_s: int, environment: Environment) -> float:
        speed = self.speed_fn(time_s)
        if self.speed_jitter_fn:
            return speed + self.speed_jitter_fn(self.time_s, speed)
        return speed

    def calculate_proper_direction_deviation(self, heading_deg: float, time_s: int, environment: Environment) -> float:
        if self.heading_jitter_fn:
            return self.heading_jitter_fn(self.time_s, heading_deg)
        return 0.0


# Todo -- model RelaySwimmerTeam 
# i.e. a team of swimmers that take over in sequence after a fixed period of time, with a fixed transition time between swimmers. 
# The system should be able to calculate the trajectory of the team as a whole.


class TimePhaseCalibration:
    """
    Class representing a time phase calibration for a currents model.
    This allows to negotiate the time phase of the currents model to match the simulation's time frame,
    The goal is to support:
     - CurrentsModels to have a pure cyclic time components behaviour unaware of absolute time 
       (e.g. a theoretical or statistical derived view on tide data); and
     - CurrentsModels that have an absolute time reference 
       (e.g. actual measured time data) 
    and be able to use them interchangeably in the same simulation framework.

    todo -- note -- this requires some agreement on the start of the cycle (e.g. first high tide in spring tide) 
    and the period of the cycle (e.g. 12h25m for a semi-diurnal tide + ??? days for a lunar cycle).
    we should use the cmems data to get a good estimate for these ...

    for now we take the peak current speed (spring-tide, 3.105 hours before high tide) 
    as this will be the most easy to identify in dataseets

    Attributes:
     - absolute_time (datetime): The absolute time to calibrate the currents model to.
     - time_offset (timedelta): The time offset to apply to the currents model's internal time reference.

    """
    def __init__(self, absolute_time: datetime | None = None, time_offset: timedelta | None = None):
        self.absolute_time = absolute_time
        self.time_offset = time_offset


class CurrentsModel(ABC):  # something that can produce a current vector for a given position and time
    """
    Abstract base class for currents model. Providfes a method to get the current vector at a given position and time.

    Note on time -- simulations will run in discrete time-steps and operate in some relative time frame.
    The CurrentsModel operates in absolute time, so the simulation will need some mechanism to deal with this. 

    Equally implementations of CurrentsModel that have a cyclic time-component (like tides) will need to be able 
    to map the requested absolute time to the cyclic time, e.g. by applying some known absolute time offset to their 
    internal time reference (start of cycle)

    Finally implementations could be limited to time and space ranges, and should raise an exception (ValueError) 
    if the requested position or time is outside of their range.
    """
    @abstractmethod
    def get_current(self, position: Position, moment: datetime) -> SpeedVector:
        """
        Get the current vector at a given position and time.
        :param position: The position to get the current vector for.
        :param moment: The time moment to get the current vector for.

        :return: The current vector at the given position and time.
        """
        pass

    @abstractmethod
    @property
    def has_absolute_time_reference(self) -> bool:
        """
        Indicates whether the currents model has an absolute time reference.
        :return: True if the currents model has an absolute time reference, False otherwise.
        """
        pass

    @abstractmethod
    def calibrate_time_phase(self, tpc: TimePhaseCalibration) -> TimePhaseCalibration:
        """
        Calibrates the time phase of the currents model based on the provided TimePhaseCalibration.
        The idea is to send in an object that either has absolute or relative time asking tthe model
        to have the other one returned, thus coupling the two and sharing them between simulation
        framework and currentsmodel.

        :param tpc: The TimePhaseCalibration to use for calibration.

        :return: The calibrated TimePhaseCalibration.
        """
        pass


class EnvironmentModel:  # something that can produce an Environment instance for a given position and time
    """
    Abstract base class for environment model. Provides a method to get an Environment instance at a given position and time. 
    """
    @abstractmethod
    def get_environment(self, position: Position, moment: datetime) -> Environment:
        """
        Get an Environment instance at a given position and time.
        :param position: The position to get the Environment instance for.
        :param moment: The time moment to get the Environment instance for.

        :return: An Environment instance at the given position and time.
        """
        pass


@dataclass
class TrajectoryResult:
    """
    Class representing the result of a trajectory calculation.
    Attributes:
        trajectory (list): A list of tuples (time_s, Position) representing the trajectory of the moving object.
        guidance (list): A list of tuples (time_s, heading_deg) representing the guidance of the moving object.
    """
    trajectory: list[(int, Position)]
    guidance: list[(int, float)]
    durartion_s: int


class TrajectoryCalculator:  # something that uses some config (size of discrete time step, ...) to calculate a trajectory for a given moving object in a given environment model
    """
    Base class for trajectory calculator. Provides a method to calculate a trajectory for a given moving object in a given environment model.
    """
    def __init__(self, time_step_s: int):
        """
        Initialize the TrajectoryCalculator with the time step in seconds.
        :param time_step_s: The time step in seconds for the trajectory calculation.
        """
        self.time_step_s = time_step_s

    def calculate_trajectory(
            self,
            moving_object: MovingObject,
            start_position: Position,
            start_time: datetime,
            heading_deg_fn: Callable[[int], float],
            duration_s: int,
            environment_model: EnvironmentModel) -> TrajectoryResult:
        """
        Calculate the trajectory for a given moving object in a given environment model.
        :param moving_object: The moving object to calculate the trajectory for.
        :param start_position: The starting position of the moving object.
        :param start_time: The starting time of the moving object.
        :param heading_deg_fn: A function that returns the heading in degrees for the moving object at a given time.
        :param duration_s: The duration in seconds for the trajectory calculation.
        :param environment_model: The environment model to use for the trajectory calculation.

        :return: A list of tuples (time_s, Position) representing the trajectory of the moving object.
        """
        moving_object.start(at=start_position, environment=environment_model.get_environment(start_position, start_time))
        trajectory = [(0, start_position)]
        guidance = [(0, heading_deg_fn(0))]
        current_time = start_time
        for timelapsed_s in range(0, duration_s, self.time_step_s):
            current_time += timedelta(seconds=self.time_step_s)
            env = environment_model.get_environment(moving_object.pos, current_time)
            heading_deg = heading_deg_fn(timelapsed_s)
            guidance.append((timelapsed_s, heading_deg))
            new_position = moving_object.move(heading_deg, self.time_step_s, env)
            trajectory.append((timelapsed_s + self.time_step_s, new_position))
        return TrajectoryResult(trajectory=trajectory, guidance=guidance, duration_s=duration_s)


class TrajectoryFinder:  # something that can find the shortest-time trajectory for a given moving object in a given environment model, given a start and end position 
    # TODO unclear how it could be made to apply different strategies to scan the space of possible guiding heading_deg_fn -- could be simply scanning different straight line headings, or a fan out variant of that by recursively re-scanning after X time_steps, or maybe even a genetic algorithm, etc.
    """
    System that can find the shortest-time trajectory for a given moving object in a given environment model, given a start and end position.
    It scans the space of possible start-times and a dynamically adjusted (generated) heading_deg_functions. 
    For each point in this space it calculates the corresponding trajectory and final time to reach a given end position.
    The best trajectory (shortest time) is returned.
    Note that the search space can be very large, so the implementation should be efficient and may need to use heuristics or approximations to find a good solution in a reasonable time.
    The search space can be defined by the user, e.g. by providing a range of start times and a range of heading_deg_functions to scan. The implementation should be able to handle different types of moving
    objects and environment models, and should be able to adapt to different scenarios and constraints.
    Scans space of possible start-times and a dynamically adjusted (generated) heading_deg_functions to calculate their corresponding trajectory and final time to reach a given end position.
    The best trajectory (shortest time) is returned.
    """
    def __init__(
            self,
            calc_time_step_s: int,
            environment_model: EnvironmentModel
        ):
        """
        Initialize the TrajectoryFinder with the time step in seconds.
        :param time_step_s: The time step in seconds for the trajectory calculation.
        """
        self.calc_time_step_s = calc_time_step_s
        self.environment_model = environment_model

    def find_optimum(
            self,
            moving_object: MovingObject,
            start_position: Position,
            end_position: Position,
            first_start_time_dt: datetime,
            last_start_time_dt: datetime,
            start_time_step_s: int,
            max_duration_s: int) -> TrajectoryResult:
        """
        Find the optimum trajectory for a given moving object in a given environment model, given a start and end position.
        :param moving_object: The moving object to calculate the trajectory for.
        :param start_position: The starting position of the moving object.
        :param end_position: The ending position of the moving object.
        :param first_start_time_dt: The first possible start time to scan.
        :param last_start_time_dt: The last possible start time to scan.
        :param start_time_step_s: The time step in seconds for the start time scan.
        :param max_duration_s: The maximum duration in seconds for the trajectory calculation.

        :return: A TrajectoryResult representing the optimum trajectory of the moving object.
        """
        best_trajectory = None
        best_time = float('inf')
        start_time_range = pd.date_range(start=first_start_time_dt, end=last_start_time_dt, freq=timedelta(seconds=start_time_step_s))
        # TODO 
        # 1. calculate bearing from start_position to end_position
        # 2. generate a heading_deg_fn that is a straight line from start_position to end_position
        # 3. create a range of heading around that and scan them all by providing a constant heading_dfeg_fn
        # 4. then for all those, run over all possible start-times
        for start_time in start_time_range:
            trajectory_calculator = TrajectoryCalculator(self.calc_time_step_s)
            trajectory_result = trajectory_calculator.calculate_trajectory(
                moving_object,
                start_position,
                start_time,
                heading_deg_fn,
                max_duration_s,
                self.environment_model
            )
            final_position = trajectory_result.trajectory[-1][1]
            if self._is_within_tolerance(final_position, end_position) and trajectory_result.duration_s < best_time:
                best_trajectory = trajectory_result
                best_time = trajectory_result.duration_s
        return best_trajectory
