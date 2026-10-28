"""Chronology, Sleep Pattern & Travel Route Tracker for Instagram OSINT.

Analyzes post timestamps and geotags to reconstruct:
1. Circadian sleep schedule & probable local timezone.
2. Chronological geolocation route, distances traveled, and travel hops.
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
    if not val:
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
    """Estimates sleep window and timezone from publication timestamps."""

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
        if total_posts < 3:
            return {
                "insufficient_data": True,
                "total_analyzed": total_posts,
                "histogram_utc": histogram,
                "sleep_window_utc": None,
                "estimated_timezone": "UTC+00:00",
                "confidence": "Low",
                "circadian_anomalies": [],
            }

        # Find best 7-hour contiguous quiet window (wrapping 24h)
        window_size = 7
        min_activity = float("inf")
        best_start = 0

        for start in range(24):
            window_sum = sum(
                histogram[(start + i) % 24] for i in range(window_size)
            )
            if window_sum < min_activity:
                min_activity = window_sum
                best_start = start

        best_end = (best_start + window_size) % 24

        # Assume natural sleep starts around 23:00 local time
        offset_hours = round(23 - best_start)
        # Normalize offset between -12 and +14
        while offset_hours > 14:
            offset_hours -= 24
        while offset_hours < -12:
            offset_hours += 24

        sign = "+" if offset_hours >= 0 else "-"
        abs_h = abs(offset_hours)
        tz_str = f"UTC{sign}{abs_h:02d}:00"

        # Confidence based on sample size and inactivity depth
        quiet_ratio = (
            (total_posts - min_activity) / total_posts if total_posts else 0
        )
        if total_posts >= 20 and quiet_ratio >= 0.85:
            confidence = "High"
        elif total_posts >= 8:
            confidence = "Medium"
        else:
            confidence = "Low"

        # Detect nocturnal anomalies (posts during sleep window)
        anomalies = []
        for dt, p in valid_posts:
            h = dt.hour
            in_window = False
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
            "total_analyzed": total_posts,
            "histogram_utc": histogram,
            "sleep_window_utc": {
                "start_hour": best_start,
                "end_hour": best_end,
                "duration_hours": window_size,
                "posts_in_window": min_activity,
            },
            "estimated_timezone": tz_str,
            "tz_offset_hours": offset_hours,
            "confidence": confidence,
            "circadian_anomalies": anomalies[:10],
        }


class TravelRouteTracker:
    """Reconstructs chronological travel trajectory from geotagged posts."""

    def analyze(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract locations, sort chronologically, and compute travel legs."""
        geotagged = []

        for p in posts:
            loc = p.get("location") or {}
            lat = loc.get("lat") or loc.get("latitude") or p.get("lat")
            lng = (
                loc.get("lng")
                or loc.get("longitude")
                or loc.get("long")
                or p.get("lng")
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
            speed_kmh = 0.0

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
                if hours_diff > 0:
                    speed_kmh = round(leg_km / hours_diff, 1)

            transit_type = "Local / Stationary"
            if leg_km > 500:
                transit_type = "Flight / Long Distance Transit"
            elif leg_km > 80:
                transit_type = "Intercity Road / Rail Travel"

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
            "total_geotagged_stops": len(geotagged),
            "total_distance_km": round(total_distance, 1),
            "unique_locations_count": len(unique_places),
            "unique_locations": unique_places,
            "route_hops": hops,
        }
