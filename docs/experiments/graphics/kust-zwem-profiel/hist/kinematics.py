"""
Alongshore Trajectory Kinematics Module.

Implements alongshore coastal tangent projection and discrete kinematic integration
along segmented coastal courses (e.g., Bredene Post 4 ➔ Vosseslag ➔ Bredene Post 4).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from typing import Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


def compute_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes initial great-circle bearing from (lat1, lon1) to (lat2, lon2) in degrees [0, 360).
    0° = North, 90° = East, 180° = South, 270° = West.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing_rad = math.atan2(y, x)
    return (math.degrees(bearing_rad) + 360.0) % 360.0


def compute_haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two points in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


@dataclass(frozen=True)
class Checkpoint:
    """Spatial checkpoint along a coastal route."""

    idx: int
    name: str
    s_km: float  # Distance from route start in km
    lat: float
    lon: float
    marker_name: Optional[str] = None


@dataclass
class LegKinematics:
    """Kinematic integration results for a single course leg."""

    leg_idx: int
    name: str
    direction: str  # 'out' or 'ret'
    from_km: float
    to_km: float
    distance_m: float
    t_start_utc: datetime
    t_end_utc: datetime
    dt_sec: float
    dt_min: float
    dist_swimmer_m: float
    dist_current_m: float
    u_avg_mps: float
    is_tailwind: bool
    is_flood: bool
    bearing_deg: float


@dataclass
class SwimmerTrajectory:
    """Trajectory simulation result for a specific swimmer water pace."""

    speed_mps: float
    start_time_utc: datetime
    finish_time_utc: datetime
    total_duration_sec: float
    total_duration_min: float
    legs: List[LegKinematics]
    checkpoint_times_utc: List[datetime]
    trajectory_points: List[Tuple[float, datetime]] = field(default_factory=list)


class AlongshoreTrajectoryCalculator:
    """
    Simulates swimmer progression along an alongshore coastal course by projecting
    2D hydrodynamic current vectors onto route leg tangents.
    """

    def __init__(
        self,
        checkpoints: List[Checkpoint],
        ds_step_m: float = 25.0,
    ):
        """
        Initialize calculator with sequential course checkpoints.
        
        Args:
            checkpoints: Ordered list of Checkpoint instances from start to finish.
            ds_step_m: Fine-grid numerical integration step in meters (default 25m).
        """
        if len(checkpoints) < 2:
            raise ValueError("Alongshore course must have at least 2 checkpoints.")
        self.checkpoints = checkpoints
        self.ds_step_m = ds_step_m

    def project_current_alongshore(
        self,
        u_east: float,
        v_north: float,
        leg_bearing_deg: float,
    ) -> float:
        """
        Projects 2D current vector (u, v) onto the direction of motion defined by leg_bearing_deg.
        
        Returns:
            Alongshore current in m/s:
            Positive = current is pushing the swimmer forward (tailwind / meegaand).
            Negative = current is opposing the swimmer (headwind / tegenstroom).
        """
        theta_rad = math.radians(leg_bearing_deg)
        # Unit vector of leg direction: (sin(theta), cos(theta)) in (East, North)
        tangent_east = math.sin(theta_rad)
        tangent_north = math.cos(theta_rad)
        return u_east * tangent_east + v_north * tangent_north

    def calculate_trajectory(
        self,
        speed_mps: float,
        start_time_utc: datetime,
        current_fn: Callable[[float, float, datetime], Tuple[float, float]],
    ) -> SwimmerTrajectory:
        """
        Performs discrete step-by-step numerical integration (ds = 25m) across all legs.
        
        Args:
            speed_mps: Swimmer cruising pace in still water (m/s).
            start_time_utc: Swimmer departure datetime (timezone-aware UTC).
            current_fn: Callable(lat, lon, datetime_utc) -> (u_east_mps, v_north_mps).
            
        Returns:
            SwimmerTrajectory containing checkpoint arrival times, leg breakdowns, and totals.
        """
        if speed_mps <= 0:
            raise ValueError(f"Swimmer water speed must be positive, got {speed_mps}")

        current_time = start_time_utc
        checkpoint_times = [current_time]
        legs_results: List[LegKinematics] = []
        trajectory_points: List[Tuple[float, datetime]] = [(self.checkpoints[0].s_km, start_time_utc)]

        total_checkpoints = len(self.checkpoints)
        for i in range(total_checkpoints - 1):
            cp_from = self.checkpoints[i]
            cp_to = self.checkpoints[i + 1]

            leg_idx = i + 1
            direction = "ret" if cp_to.s_km <= cp_from.s_km else "out"
            leg_distance_m = compute_haversine_distance_m(cp_from.lat, cp_from.lon, cp_to.lat, cp_to.lon)
            bearing_deg = compute_bearing_deg(cp_from.lat, cp_from.lon, cp_to.lat, cp_to.lon)

            # Numerical integration along leg in steps of ds_step_m
            num_steps = max(1, int(math.ceil(leg_distance_m / self.ds_step_m)))
            actual_ds = leg_distance_m / num_steps

            leg_t_start = current_time
            leg_dist_swimmer = 0.0
            leg_dist_current = 0.0
            u_alongshore_samples = []

            for step in range(num_steps):
                frac = (step + 0.5) / num_steps
                cur_lat = cp_from.lat + frac * (cp_to.lat - cp_from.lat)
                cur_lon = cp_from.lon + frac * (cp_to.lon - cp_from.lon)

                # Query 2D hydrodynamic current
                u_east, v_north = current_fn(cur_lat, cur_lon, current_time)
                u_along = self.project_current_alongshore(u_east, v_north, bearing_deg)
                u_alongshore_samples.append(u_along)

                v_ground = speed_mps + u_along
                # Physical safety clamp: ground speed must remain positive to progress
                if v_ground < 0.02:
                    v_ground = 0.02

                dt_step_sec = actual_ds / v_ground
                current_time += timedelta(seconds=dt_step_sec)

                leg_dist_swimmer += speed_mps * dt_step_sec
                leg_dist_current += u_along * dt_step_sec

                cur_s_km = cp_from.s_km + (step + 1) / num_steps * (cp_to.s_km - cp_from.s_km)
                trajectory_points.append((cur_s_km, current_time))

            leg_dt_sec = (current_time - leg_t_start).total_seconds()
            leg_dt_min = leg_dt_sec / 60.0
            u_avg = np.mean(u_alongshore_samples)

            # Determine flood / ebb character (Belgian coast: 20° to 110° is Flood / eastward)
            mean_curr_dir = (math.degrees(math.atan2(np.mean([u_along]), 0.0)) + 360) % 360
            is_flood = (20.0 <= bearing_deg <= 110.0 and u_avg > 0) or (
                not (20.0 <= bearing_deg <= 110.0) and u_avg < 0
            )

            leg_kin = LegKinematics(
                leg_idx=leg_idx,
                name=f"Leg {leg_idx}/{total_checkpoints - 1}",
                direction=direction,
                from_km=cp_from.s_km,
                to_km=cp_to.s_km,
                distance_m=leg_distance_m,
                t_start_utc=leg_t_start,
                t_end_utc=current_time,
                dt_sec=leg_dt_sec,
                dt_min=leg_dt_min,
                dist_swimmer_m=leg_dist_swimmer,
                dist_current_m=leg_dist_current,
                u_avg_mps=float(u_avg),
                is_tailwind=bool(u_avg > 0),
                is_flood=bool(is_flood),
                bearing_deg=bearing_deg,
            )
            legs_results.append(leg_kin)
            checkpoint_times.append(current_time)

        total_duration_sec = (current_time - start_time_utc).total_seconds()
        return SwimmerTrajectory(
            speed_mps=speed_mps,
            start_time_utc=start_time_utc,
            finish_time_utc=current_time,
            total_duration_sec=total_duration_sec,
            total_duration_min=total_duration_sec / 60.0,
            legs=legs_results,
            checkpoint_times_utc=checkpoint_times,
            trajectory_points=trajectory_points,
        )
