"""
SmartGuard AI — Models package initializer.
Import all models here so Alembic autogenerate can discover them.
"""
from app.models.account import SecurityAccount, AuditLog  # noqa: F401
from app.models.people import (  # noqa: F401
    CampusPerson,
    Vehicle,
    FaceProfile,
    FaceVerification,
    AlprVerification,
)
from app.models.access import (  # noqa: F401
    AccessSchedule,
    WatchlistEntry,
    AccessAttempt,
)
from app.models.alerts import (  # noqa: F401
    SecurityAlert,
    AlertNote,
    SecurityContact,
    NotificationLog,
)
from app.models.visitors import (  # noqa: F401
    VisitorPass,
    VisitorApproval,
)
