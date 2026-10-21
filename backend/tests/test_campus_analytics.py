from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.campus_analytics_service import (
    get_campus_analytics,
    local_day_utc_bounds,
)


def test_local_day_utc_bounds_uses_campus_timezone():
    start, end = local_day_utc_bounds(
        datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        "Asia/Kolkata",
    )

    assert start == datetime(2025, 1, 1, 18, 30, tzinfo=timezone.utc)
    assert end == datetime(2025, 1, 2, 18, 30, tzinfo=timezone.utc)


def test_local_day_utc_bounds_rejects_naive_reference_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        local_day_utc_bounds(datetime(2025, 1, 1, 12, 0), "Asia/Kolkata")


def test_invalid_campus_timezone_is_not_silently_ignored():
    with pytest.raises(ValueError, match="Invalid campus timezone"):
        local_day_utc_bounds(
            datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            "Invalid/Timezone",
        )


def test_analytics_counts_denials_and_labels_authorizations_as_unverified():
    db = MagicMock()
    timezone_result = MagicMock()
    timezone_result.scalar_one_or_none.return_value = "Asia/Kolkata"
    grouped_result = MagicMock()
    grouped_result.all.return_value = [
        ("ENTRY", "ALLOW", 8, 2),
        ("EXIT", "ALLOW", 9, 1),
        ("ENTRY", "DENY", 8, 3),
        ("EXIT", "MANUAL_REVIEW", 10, 4),
    ]
    recent_result = MagicMock()
    recent_result.all.return_value = [
        (
            "attempt-1",
            datetime(2025, 1, 2, 5, 0, tzinfo=timezone.utc),
            "Visitor One",
            "visitor",
            "ENTRY",
            "ALLOW",
        )
    ]
    db.execute.side_effect = [timezone_result, grouped_result, recent_result]

    analytics = get_campus_analytics(
        db,
        datetime(2025, 1, 2, 5, 30, tzinfo=timezone.utc),
    )

    assert analytics.denied_access_today == 3
    assert analytics.total_entries_today is None
    assert analytics.total_exits_today is None
    assert analytics.currently_inside is None
    assert analytics.occupancy_by_category is None
    assert analytics.hourly_activity[8].entry_authorizations == 2
    assert analytics.hourly_activity[9].exit_authorizations == 1
    assert analytics.hourly_activity[10].exit_authorizations == 0
    assert analytics.recent_activity[0].person_name == "Visitor One"
    assert analytics.recent_activity[0].person_category == "visitor"
    assert analytics.recent_activity[0].movement_status == "NOT_VERIFIED"
    assert "no sensor-confirmed" in analytics.movement_limitation.lower()
    assert db.execute.call_count == 3
    compiled_queries = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in db.execute.call_args_list
    ]
    assert "TIMEZONE" in compiled_queries[1].upper()


def test_endpoint_exposes_supported_analytics_response(client, mock_db, security_account):
    from app.api.dependencies import require_security
    from app.db.session import get_db
    from app.main import app

    timezone_result = MagicMock()
    timezone_result.scalar_one_or_none.return_value = "Asia/Kolkata"
    grouped_result = MagicMock()
    grouped_result.all.return_value = []
    recent_result = MagicMock()
    recent_result.all.return_value = []
    mock_db.execute.side_effect = [timezone_result, grouped_result, recent_result]

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[require_security] = lambda: security_account
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/api/access/analytics/campus")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 200
    data = response.json()
    assert data["movement_tracking_available"] is False
    assert data["total_entries_today"] is None
    assert data["currently_inside"] is None
    assert data["total_exits_today"] is None
    assert data["denied_access_today"] == 0
    assert data["occupancy_by_category"] is None
    assert set(data["supported_person_categories"]) == {
        "student",
        "staff",
        "visitor",
        "contractor",
    }
    assert len(data["hourly_activity"]) == 24
