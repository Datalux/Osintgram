"""Chronology, Sleep Pattern & Travel Route Tracker for Instagram OSINT.

Analyzes post timestamps and geotags to reconstruct:
1. Circadian sleep schedule & probable local timezone (rough estimate).
2. Chronological geolocation route, distances traveled, and travel hops.

Note: Rough estimates, not evidence. Geotags and post timestamps do not prove
physical presence, and social media activity does not reliably reflect sleep.
"""
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in kilometers."""
    radius_earth_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return round(radius_earth_km * c, 1)


def parse_timestamp(val: Any) -> Optional[datetime]:
    """Parse various timestamp representations into UTC datetime."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        val = val.strip()
        if val.isdigit():
            try:
                return datetime.fromtimestamp(int(val), tz=timezone.utc)
            except Exception:
                return None
        # ISO format try
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


class SleepScheduleAnalyzer:
    """Estimates sleep window and timezone range from publication timestamps.

    Disclaimer: Rough estimate, not evidence. Social media activity does not
    reliably reflect sleep or physical presence (scheduled posts, nocturnal habits,
    and irregular routines can significantly skew results).
    """

    def analyze(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Infer sleep window and timezone from 24h activity histogram."""
        histogram = [0] * 24
        valid_posts = []

        for p in posts:
            raw_ts = (
                p.get("taken_at")
                or p.get("taken_at_timestamp")
                or p.get("timestamp")
            )
            dt = parse_timestamp(raw_ts)
            if dt:
                histogram[dt.hour] += 1
                valid_posts.append((dt, p))

        total_posts = len(valid_posts)
        disclaimer_text = (
            "Rough estimate, not evidence. Social media activity does not "
            "reliably reflect sleep or physical presence."
        )

        if total_posts < 3:
            return {
                "insufficient_data": True,
                "disclaimer": disclaimer_text,
                "total_analyzed": total_posts,
                "histogram_utc": histogram,
                "sleep_window_utc": None,
                "estimated_timezone": "Unknown (Insufficient data)",
                "confidence": "Low",
                "is_ambiguous": True,
                "circadian_anomalies": [],
            }

        # 7-hour contiguous quiet window (wrapping 24h)
        window_size = 7
        window_sums = [
            sum(histogram[(start + i) % 24] for i in range(window_size))
            for start in range(24)
        ]
        min_activity = min(window_sums)
        tied_starts = [start for start, s in enumerate(window_sums) if s == min_activity]

        # Handle ties: pick the center of the longest contiguous run of tied start hours
        def get_center_start(starts: List[int]) -> int:
            if not starts:
                return 0
            if len(starts) == 1:
                return starts[0]
            # Identify contiguous runs
            runs = []
            curr = [starts[0]]
            for i in range(1, len(starts)):
                if starts[i] == starts[i - 1] + 1:
                    curr.append(starts[i])
                else:
                    runs.append(curr)
                    curr = [starts[i]]
            runs.append(curr)

            # Check circular wrap (starts[0] == 0 and starts[-1] == 23)
            if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == 23:
                wrapped_run = runs[-1] + runs[0]
                runs = runs[1:-1] + [wrapped_run]

            longest_run = max(runs, key=len)
            mid_val = longest_run[len(longest_run) // 2]
            return mid_val % 24

        best_start = get_center_start(tied_starts)
        best_end = (best_start + window_size) % 24

        # Ambiguity: more than 1 tied window or completely flat
        expected_window = total_posts * (window_size / 24.0)
        depth = 1.0 - (min_activity / expected_window) if expected_window > 0 else 0.0
        is_ambiguous = len(tied_starts) > 1 or depth < 0.2

        # Present timezone as a range / rough estimate:
        # Assuming natural sleep window start falls between 22:00 and 01:00 local time:
        def norm_offset(h: int) -> int:
            while h > 14:
                h -= 24
            while h < -12:
                h += 24
            return h

        def fmt_tz(offset: int) -> str:
            sign = "+" if offset >= 0 else "-"
            return f"UTC{sign}{abs(offset):02d}:00"

        offset_min = norm_offset(22 - best_start)
        offset_max = norm_offset(25 - best_start)
        if offset_min > offset_max:
            offset_min, offset_max = offset_max, offset_min

        tz_str = f"{fmt_tz(offset_min)} to {fmt_tz(offset_max)} (rough estimate)"

        # Confidence based on quiet window depth relative to average and ambiguity
        if is_ambiguous or depth < 0.4 or total_posts < 8:
            confidence = "Low"
        elif total_posts >= 25 and depth >= 0.75:
            confidence = "High"
        else:
            confidence = "Medium"

        # Detect nocturnal anomalies
        anomalies = []
        for dt, p in valid_posts:
            h = dt.hour
            if best_start <= best_end:
                in_window = best_start <= h < best_end
            else:
                in_window = (h >= best_start) or (h < best_end)

            if in_window:
                anomalies.append({
                    "post_id": str(p.get("id") or p.get("pk") or ""),
                    "timestamp_utc": dt.isoformat(),
                    "hour_utc": h,
                    "caption": (
                        (p.get("caption") or {}).get("text")
                        if isinstance(p.get("caption"), dict)
                        else str(p.get("caption") or "")
                    )[:60],
                })

        return {
            "insufficient_data": False,
            "disclaimer": disclaimer_text,
            "total_analyzed": total_posts,
            "histogram_utc": histogram,
            "sleep_window_utc": {
                "start_hour": best_start,
                "end_hour": best_end,
                "duration_hours": window_size,
                "posts_in_window": min_activity,
                "candidate_start_hours": tied_starts,
            },
            "estimated_timezone": tz_str,
            "tz_offset_hours": round((offset_min + offset_max) / 2),
            "tz_offset_range": [offset_min, offset_max],
            "quiet_depth_ratio": round(depth, 2),
            "is_ambiguous": is_ambiguous,
            "confidence": confidence,
            "circadian_anomalies": anomalies[:10],
        }


class TravelRouteTracker:
    """Reconstructs chronological travel trajectory from geotagged posts.

    Disclaimer: Geotags and post timestamps do not prove physical presence:
    users frequently tag locations remotely, after traveling, or on old photos.
    """

    def analyze(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract locations, sort chronologically, and compute travel legs."""
        geotagged = []

        def _first_coord(*values):
            for v in values:
                if v is not None:
                    return v
            return None

        for p in posts:
            loc = p.get("location") or {}
            lat = _first_coord(loc.get("lat"), loc.get("latitude"), p.get("lat"))
            lng = _first_coord(
                loc.get("lng"), loc.get("longitude"), loc.get("long"), p.get("lng")
            )
            raw_ts = (
                p.get("taken_at")
                or p.get("taken_at_timestamp")
                or p.get("timestamp")
            )
            dt = parse_timestamp(raw_ts)

            if lat is not None and lng is not None and dt:
                try:
                    lat_f = float(lat)
                    lng_f = float(lng)
                    loc_name = (
                        loc.get("name")
                        or loc.get("title")
                        or "Unknown location"
                    )
                    geotagged.append({
                        "post_id": str(p.get("id") or p.get("pk") or ""),
                        "timestamp": dt,
                        "timestamp_iso": dt.isoformat(),
                        "location_name": loc_name,
                        "city": loc.get("city") or "",
                        "lat": lat_f,
                        "lng": lng_f,
                    })
                except (ValueError, TypeError):
                    continue

        # Sort chronologically ascending
        geotagged.sort(key=lambda x: x["timestamp"])

        total_distance = 0.0
        hops = []
        unique_places = []
        seen_names = set()

        for i, stop in enumerate(geotagged):
            name = stop["location_name"]
            if name and name not in seen_names:
                seen_names.add(name)
                unique_places.append(name)

            leg_km = 0.0
            days_gap = 0.0
            speed_kmh = None

            if i > 0:
                prev = geotagged[i - 1]
                leg_km = haversine_km(
                    prev["lat"], prev["lng"], stop["lat"], stop["lng"]
                )
                total_distance += leg_km
                seconds_diff = max(
                    1, (stop["timestamp"] - prev["timestamp"]).total_seconds()
                )
                days_gap = round(seconds_diff / 86400.0, 1)
                hours_diff = seconds_diff / 3600.0
                # Meaningful speed only computed for short intervals (<= 48 hours)
                if 0 < hours_diff <= 48.0:
                    speed_kmh = round(leg_km / hours_diff, 1)

            # Classify transit using both distance and time gap
            if leg_km == 0.0:
                transit_type = "Same Location / Co-located"
            elif days_gap > 3.0:
                transit_type = f"Distant post ({leg_km:.0f} km, {days_gap:.0f}d gap)"
            elif leg_km > 500:
                transit_type = "Likely Flight / Fast Transit"
            elif leg_km > 80:
                transit_type = "Intercity Road / Rail Travel"
            else:
                transit_type = "Local / Stationary"

            hops.append({
                "sequence": i + 1,
                "post_id": stop["post_id"],
                "date": stop["timestamp_iso"][:10],
                "datetime_utc": stop["timestamp_iso"],
                "location": stop["location_name"],
                "coordinates": [stop["lat"], stop["lng"]],
                "distance_from_prev_km": leg_km,
                "days_since_prev": days_gap,
                "speed_kmh": speed_kmh,
                "transit_type": transit_type,
            })

        return {
            "disclaimer": (
                "Geotags indicate tagged locations, not verified physical presence "
                "(posts may be retroactive or tagged remotely)."
            ),
            "total_geotagged_stops": len(geotagged),
            "total_distance_km": round(total_distance, 1),
            "unique_locations_count": len(unique_places),
            "unique_locations": unique_places,
            "route_hops": hops,
        }
