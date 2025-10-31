# scheduler/services/generation/heuristic.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from scheduler.services.distance import get_leg_duration

# ---- Your models (adjust field names if different) ---------------------------
from scheduler.models import (
    Driver,        # id, name, active:bool, (optionally) home_base_lat/lng
    JobRequest,    # id, client_id, date, window_start, window_end, duration_minutes, status
    ScheduleEntry, # id, job_request, driver, date, start_time, end_time, status, route_start_lat/lng, route_end_lat/lng
    Client,        # id, name, pickup_lat/lng, dropoff_lat/lng
)

# ---- Options -----------------------------------------------------------------
@dataclass
class Options:
    day: date
    start_of_service: time = time(7, 0)   # depot open
    end_of_service:   time = time(19, 0)  # depot close
    max_lateness_min: int = 0             # set to >0 to allow soft lateness
    assume_homebase:  bool = True         # use driver.home_base_* as depots if present

# ---- Internal structures ------------------------------------------------------
@dataclass
class Stop:
    job: JobRequest
    arrive: datetime
    start: datetime
    depart: datetime
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float

@dataclass
class Route:
    driver: Driver
    stops: List[Stop]

# ---- Utilities ----------------------------------------------------------------
def _start_of_day_local(day: date) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time(0,0)), tz)

def _clip_to_window(t: datetime, window_start: time) -> datetime:
    ws = datetime.combine(t.date(), window_start, tzinfo=t.tzinfo)
    return t if t >= ws else ws

# ---- Feasibility + insertion --------------------------------------------------
def _simulate_insert(route: Route, job: JobRequest, opts: Options) -> Tuple[bool, int, List[Stop]]:
    """
    Try to insert 'job' at the best position in 'route'.
    Returns (feasible, penalty, new_stops_if_chosen)
    Penalty is total lateness minutes + tiny tie-breaker on drive.
    Very small+fast, good enough to ship.
    """
    # Resolve coordinates (pickup -> dropoff)
    client = job.client
    s_lat, s_lng = client.pickup_lat, client.pickup_lng
    e_lat, e_lng = client.dropoff_lat, client.dropoff_lng

    if s_lat is None or s_lng is None or e_lat is None or e_lng is None:
        return (False, 10**9, [])

    # Build a working list including a synthetic "start node" at driver base
    tz = timezone.get_current_timezone()
    day0 = _start_of_day_local(job.date)
    service_open = datetime.combine(job.date, opts.start_of_service, tzinfo=tz)
    # starting point for the route:
    if route.stops:
        start_lat = route.stops[0].start_lat
        start_lng = route.stops[0].start_lng
    else:
        start_lat = getattr(route.driver, "home_base_lat", None) if opts.assume_homebase else s_lat
        start_lng = getattr(route.driver, "home_base_lng", None) if opts.assume_homebase else s_lng
        if start_lat is None or start_lng is None:
            start_lat, start_lng = s_lat, s_lng

    best_penalty = 10**9
    best_plan: List[Stop] = []
    original = route.stops

    # We'll try inserting between every pair of existing stops (including ends)
    n = len(original)
    for k in range(n + 1):
        plan: List[Stop] = []
        lateness_total = 0
        drive_tiebreak = 0

        # step through each segment, creating a forward scheduled timeline
        cur_lat = start_lat
        cur_lng = start_lng
        cur_time = service_open

        for i in range(n + 1):
            if i == k:  # place the new job here
                # travel to pickup
                leg1 = get_leg_duration(cur_lat, cur_lng, s_lat, s_lng, cur_time)
                arrive_pickup = cur_time + timedelta(seconds=leg1.duration_sec)
                # respect the job window
                window_start = datetime.combine(job.date, job.window_start, tzinfo=tz) if job.window_start else service_open
                start_service = max(arrive_pickup, window_start)
                # lateness if past window_end
                window_end = datetime.combine(job.date, job.window_end, tzinfo=tz) if job.window_end else None
                if window_end and start_service > window_end + timedelta(minutes=opts.max_lateness_min):
                    plan = []  # infeasible
                    break

                depart_pickup = start_service + timedelta(minutes=job.duration_minutes or 0)
                # travel to dropoff (we treat the whole job as a single block for routing;
                # if you want pickup+dropoff as two stops, split here)
                leg2 = get_leg_duration(s_lat, s_lng, e_lat, e_lng, depart_pickup)
                arrive_drop = depart_pickup + timedelta(seconds=leg2.duration_sec)

                plan.append(Stop(
                    job=job, arrive=arrive_pickup, start=start_service, depart=arrive_drop,
                    start_lat=s_lat, start_lng=s_lng, end_lat=e_lat, end_lng=e_lng
                ))

                # update cursor
                cur_lat, cur_lng = e_lat, e_lng
                cur_time = arrive_drop
                drive_tiebreak += leg1.duration_sec + leg2.duration_sec
                if window_end and start_service > window_end:
                    late_min = int((start_service - window_end).total_seconds() // 60)
                    lateness_total += late_min

            if i < n:  # add the original stop i
                st = original[i]
                # drive from current to that job's pickup
                legX = get_leg_duration(cur_lat, cur_lng, st.start_lat, st.start_lng, cur_time)
                arriveX = cur_time + timedelta(seconds=legX.duration_sec)
                # enforce that original stop still meets its window (approx: reuse its request)
                rq = st.job
                wstart = datetime.combine(rq.date, rq.window_start, tzinfo=tz) if rq.window_start else service_open
                startX = max(arriveX, wstart)
                wend = datetime.combine(rq.date, rq.window_end, tzinfo=tz) if rq.window_end else None
                if wend and startX > wend + timedelta(minutes=opts.max_lateness_min):
                    plan = []
                    break
                departX = startX + timedelta(minutes=rq.duration_minutes or 0)
                legY = get_leg_duration(st.start_lat, st.start_lng, st.end_lat, st.end_lng, departX)
                arriveY = departX + timedelta(seconds=legY.duration_sec)

                plan.append(Stop(
                    job=rq, arrive=arriveX, start=startX, depart=arriveY,
                    start_lat=st.start_lat, start_lng=st.start_lng,
                    end_lat=st.end_lat, end_lng=st.end_lng
                ))
                cur_lat, cur_lng = st.end_lat, st.end_lng
                cur_time = arriveY
                drive_tiebreak += legX.duration_sec + legY.duration_sec
                if wend and startX > wend:
                    late_min = int((startX - wend).total_seconds() // 60)
                    lateness_total += late_min

        if not plan:
            continue
        penalty = lateness_total * 10_000 + drive_tiebreak  # lateness dominates
        if penalty < best_penalty:
            best_penalty = penalty
            best_plan = plan

    return (bool(best_plan), best_penalty, best_plan)

# ---- Main entrypoint ----------------------------------------------------------
@dataclass
class GenerationResult:
    created: int
    unscheduled: List[Dict]
    metrics: Dict[str, int]

def generate_for_day(day: date, *, overwrite: bool = False, max_lateness_min: int = 0) -> GenerationResult:
    """
    Pulls all pending JobRequests for 'day', active drivers,
    and assigns greedily using best-insertion per driver.
    """
    opts = Options(day=day, max_lateness_min=max_lateness_min)

    drivers = list(Driver.objects.filter(active=True))
    if not drivers:
        return GenerationResult(created=0, unscheduled=[{"reason":"no_drivers"}], metrics={})

    jobs = list(JobRequest.objects
                .select_related("client")
                .filter(date=day, status="pending")
                .order_by("window_start", "priority"))

    routes: Dict[int, Route] = {d.id: Route(driver=d, stops=[]) for d in drivers}
    created = 0
    unscheduled = []
    late_total = 0

    for job in jobs:
        best = None  # (driver_id, penalty, new_plan)
        for d in drivers:
            feasible, penalty, new_plan = _simulate_insert(routes[d.id], job, opts)
            if feasible and (best is None or penalty < best[1]):
                best = (d.id, penalty, new_plan)

        if not best:
            unscheduled.append({"job_id": job.id, "reason": "no_feasible_slot"})
            continue

        d_id, penalty, new_plan = best
        routes[d_id].stops = new_plan
        # count lateness for metrics
        late_total += (penalty // 10_000)

    # Persist
    from django.db.models import Q
    with transaction.atomic():
        if overwrite:
            ScheduleEntry.objects.filter(date=day).delete()

        bulk = []
        for r in routes.values():
            for st in r.stops:
                bulk.append(ScheduleEntry(
                    job_request=st.job,
                    driver=r.driver,
                    date=day,
                    start_time=st.start.timetz(),  # keep tz-aware -> naive time
                    end_time=st.depart.timetz(),
                    status="scheduled",
                    route_start_lat=st.start_lat,
                    route_start_lng=st.start_lng,
                    route_end_lat=st.end_lat,
                    route_end_lng=st.end_lng,
                ))
        ScheduleEntry.objects.bulk_create(bulk)
        # flip job status
        JobRequest.objects.filter(id__in=[s.job.id for r in routes.values() for s in r.stops]).update(status="scheduled")

        created = len(bulk)

    return GenerationResult(
        created=created,
        unscheduled=unscheduled,
        metrics={"late_minutes": late_total, "drivers_used": sum(1 for r in routes.values() if r.stops)}
    )
