"""Unit tests for Chronology, Sleep Pattern & Travel Route Tracker."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.chronology_tracker import (
    SleepScheduleAnalyzer,
    TravelRouteTracker,
    haversine_km,
    parse_timestamp,
)
from src.osint_service import OsintgramService, PrivateProfileError
from src.web.tools import build_tools, tool_specs


def test_haversine_km():
    # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ~ 343 km
    dist = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 340 <= dist <= 350

    # Same coordinate is 0 km
    assert haversine_km(52.2297, 21.0122, 52.2297, 21.0122) == 0.0


def test_parse_timestamp():
    dt_epoch = parse_timestamp(1700000000)
    assert dt_epoch == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    dt_str = parse_timestamp("1700000000")
    assert dt_str == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    dt_iso = parse_timestamp("2024-05-10T15:30:00Z")
    assert dt_iso == datetime(2024, 5, 10, 15, 30, tzinfo=timezone.utc)

    assert parse_timestamp(None) is None
    assert parse_timestamp("invalid-date") is None


def test_sleep_schedule_insufficient_data():
    analyzer = SleepScheduleAnalyzer()
    res = analyzer.analyze([{"taken_at": 1700000000}])
    assert res["insufficient_data"] is True
    assert res["total_analyzed"] == 1


def test_sleep_schedule_pattern_and_anomalies():
    analyzer = SleepScheduleAnalyzer()

    # Create posts between 08:00 and 22:00 UTC (quiet window 23:00 - 06:00 UTC)
    posts = []
    base_ts = 1700000000  # Nov 14, 2023
    for hour in range(8, 22):
        dt = datetime(2024, 1, 15, hour, 15, tzinfo=timezone.utc)
        posts.append({"id": f"p_{hour}", "taken_at": dt.timestamp()})

    # Add a nocturnal anomaly at 02:30 UTC
    dt_night = datetime(2024, 1, 16, 2, 30, tzinfo=timezone.utc)
    posts.append({
        "id": "p_night",
        "taken_at": dt_night.timestamp(),
        "caption": {"text": "Can't sleep, jet lag!"},
    })

    res = analyzer.analyze(posts)
    assert res["insufficient_data"] is False
    assert res["total_analyzed"] == len(posts)

    win = res["sleep_window_utc"]
    assert win is not None
    # Quietest window starts around 23:00 - 00:00 UTC
    assert 22 <= win["start_hour"] or win["start_hour"] <= 1
    assert "UTC" in res["estimated_timezone"]

    # Nocturnal anomaly detected
    assert len(res["circadian_anomalies"]) >= 1
    assert any(a["post_id"] == "p_night" for a in res["circadian_anomalies"])


def test_travel_route_tracker():
    tracker = TravelRouteTracker()

    posts = [
        # Stop 1: Warsaw (2024-01-01)
        {
            "id": "stop1",
            "taken_at": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp(),
            "location": {"name": "Warsaw Old Town", "lat": 52.2297, "lng": 21.0122},
        },
        # Stop 2: Berlin (2024-01-05) ~517 km from Warsaw
        {
            "id": "stop2",
            "taken_at": datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc).timestamp(),
            "location": {"name": "Berlin Alexanderplatz", "lat": 52.5200, "lng": 13.4050},
        },
        # Stop 3: Paris (2024-01-10) ~878 km from Berlin
        {
            "id": "stop3",
            "taken_at": datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc).timestamp(),
            "location": {"name": "Eiffel Tower", "lat": 48.8584, "lng": 2.2945},
        },
    ]

    res = tracker.analyze(posts)
    assert res["total_geotagged_stops"] == 3
    assert res["unique_locations_count"] == 3
    assert res["total_distance_km"] > 1300

    hops = res["route_hops"]
    assert len(hops) == 3
    assert hops[0]["location"] == "Warsaw Old Town"
    assert hops[0]["distance_from_prev_km"] == 0.0

    assert hops[1]["location"] == "Berlin Alexanderplatz"
    assert 500 <= hops[1]["distance_from_prev_km"] <= 530
    assert hops[1]["days_since_prev"] == 4.0
    assert "Flight" in hops[1]["transit_type"] or "Travel" in hops[1]["transit_type"]

    assert hops[2]["location"] == "Eiffel Tower"
    assert 850 <= hops[2]["distance_from_prev_km"] <= 900
    assert hops[2]["days_since_prev"] == 5.0


def test_osint_service_sleep_and_travel_integration():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": False}
    }
    mock_api.user_medias_g2.return_value = {
        "response": {
            "items": [
                {
                    "id": "post_1",
                    "taken_at": 1700000000,
                    "location": {"name": "Rome Colosseum", "lat": 41.8902, "lng": 12.4922},
                },
                {
                    "id": "post_2",
                    "taken_at": 1700100000,
                    "location": {"name": "Milan Duomo", "lat": 45.4642, "lng": 9.1919},
                },
            ]
        },
        "next_page_id": None,
    }

    service = OsintgramService("alice", mock_api)
    sleep_data = service.get_sleep_schedule(limit_posts=10)
    assert "sleep_window_utc" in sleep_data

    travel_data = service.get_travel_route(limit_posts=10)
    assert travel_data["total_geotagged_stops"] == 2
    assert travel_data["total_distance_km"] > 400


def test_private_profile_guard():
    mock_api = MagicMock()
    mock_api.user_by_username_v2.return_value = {
        "user": {"pk": "100", "username": "alice", "is_private": True}
    }
    service = OsintgramService("alice", mock_api)

    with pytest.raises(PrivateProfileError):
        service.get_sleep_schedule()

    with pytest.raises(PrivateProfileError):
        service.get_travel_route()


def test_tools_specs_and_execution():
    specs = tool_specs()
    sleep_spec = next((s for s in specs if s["name"] == "get_sleep_schedule"), None)
    assert sleep_spec is not None
    assert any(p["name"] == "limit_posts" for p in sleep_spec["params"])

    travel_spec = next((s for s in specs if s["name"] == "get_travel_route"), None)
    assert travel_spec is not None
    assert any(p["name"] == "limit_posts" for p in travel_spec["params"])

    mock_service = MagicMock()
    mock_service.get_sleep_schedule.return_value = {"confidence": "High"}
    mock_service.get_travel_route.return_value = {"total_distance_km": 120.0}

    tools = build_tools(mock_service)
    sleep_fn = next((t for t in tools if t.__name__ == "get_sleep_schedule"), None)
    travel_fn = next((t for t in tools if t.__name__ == "get_travel_route"), None)

    assert sleep_fn is not None and "High" in sleep_fn(limit_posts=10)
    assert travel_fn is not None and "120" in travel_fn(limit_posts=10)
