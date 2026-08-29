# src/cscm/moon/phases.py

from skyfield import almanac
from skyfield.api import load
from datetime import datetime

# 1. Laad de astronomische data van NASA (JPL ephemeris)
eph = load('de421.bsp')
ts = load.timescale()
phases = [
    ("new moon", 0),
    ("1st qrtr", 90),
    ("full moon", 180),
    ("last qrtr", 270),
]


def datetime_to_ts(dt: datetime):
    """Convert a datetime object to a Skyfield Time object."""
    return ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def get_phases(t0: datetime, t1: datetime):
    """
    Returns a list of tuples with the moon phases between t0 and t1.
    Each tuple contains:
    - the datetime of the phase (in UTC)
    - the index of the phase (0: new moon, 1: first quarter, 2: full moon, 3: last quarter)
    - the name of the phase
    - the angle of the phase in degrees
    """
    t, y = almanac.find_discrete(datetime_to_ts(t0), datetime_to_ts(t1), almanac.moon_phases(eph))
    return [
        (
            ti.utc_datetime(),
            pndx,
            phases[pndx][0],
            phases[pndx][1],
        )
        for ti, pndx in zip(t, y)
    ]


Mooncycle = tuple[datetime, datetime, float, float]  # start_dt, end_dt, lunarperiod_d, tidalperiod_h


def get_newmoon_cycles(t0: datetime, t1: datetime) -> list[Mooncycle]:
    """
    Returns a list of tuples with the new moon phases between t0 and t1.
    Each tuple contains:
    - the start-date of the cycle (in UTC) - ie the data of the new moon
    - the end-date of the cycle (in UTC) - ie the data of the next new moon
    - the lenght of the cycle in sun-days on earth (ie the time between two new moons)
    - the lenght of the tidal cycle in hours on earth (ie the averag time between two high-tides)
    """
    phases = get_phases(t0, t1)
    newmoon_dts = [phase[0] for phase in phases if phase[1] == 0]
    newmoon_cycles = []
    for i in range(len(newmoon_dts) - 1):
        start_dt = newmoon_dts[i]
        end_dt = newmoon_dts[i + 1]
        lunarperiod_s = (end_dt - start_dt).total_seconds()
        lunarperiod_d = lunarperiod_s / 86400  # this is expressed in "sun-days"
        lunarperiod_ld = lunarperiod_d - 1  # tide is impacted by "lunar days" -- in this time that is exactly 1 sun day less
        tidalperiod_d = lunarperiod_d / (2 * lunarperiod_ld)  # twice as many full tide-cycles will exist in that period
        tidalperiod_h = tidalperiod_d * 24  # in hours

        newmoon_cycles.append(
            (
                start_dt,
                end_dt,
                lunarperiod_d,
                tidalperiod_h,
            )
        )
    return newmoon_cycles


def main():
    start_date: datetime = datetime(2022, 1, 1)
    now: datetime = datetime.now()
    end_date: datetime = datetime(now.year, now.month + 1, 15)  # till halfway next month
    phases: list = get_phases(start_date, end_date)

    print("\nMoon Phases:")
    print(f"{'Datum & Tijd (UTC)':<25} | Fase (naam, hoek °)")
    print("-" * 50)
    # print some slice (last 10) of the result as showcase
    for dt, ndx, name, angle in phases[-10:]:
        print(f"{dt.strftime('%Y-%m-%d %H:%M:%S UTC'):<25} | ({name:<9}, {angle:5.1f}°)")

    newmoon_cycles = get_newmoon_cycles(start_date, end_date)
    print("\nNew Moon Cycles:")
    print(f"{'Start (UTC)':<25} | {'End (UTC)':<25} | {'Lunar Period (days)':<20} | {'Tidal Period (hours)':<20}")
    print("-" * 100)
    # print some slice (last 10) of the result as showcase
    for start_dt, end_dt, lunarperiod_d, tidalperiod_h in newmoon_cycles[-10:]:
        print(
            f"{start_dt.strftime('%Y-%m-%d %H:%M:%S UTC'):<25} | "
            f"{end_dt.strftime('%Y-%m-%d %H:%M:%S UTC'):<25} | "
            f"{lunarperiod_d:>20.5f} | "
            f"{tidalperiod_h:>20.5f}"
        )


if __name__ == "__main__":
    main()
