"""Database operations for application settings.

Provides CRUD operations for the settings table (singleton row).
Settings are organized into logical groups for easier management.
"""

from .read import (
    get_all_settings,
    get_channel_numbering_settings,
    get_dispatcharr_settings,
    get_display_settings,
    get_epg_settings,
    get_lifecycle_settings,
    get_scheduler_settings,
    get_stream_filter_settings,
    get_team_filter_settings,
)
from .types import (
    AllSettings,
    APISettings,
    ChannelNumberingSettings,
    DispatcharrSettings,
    DisplaySettings,
    DurationSettings,
    EPGSettings,
    LifecycleSettings,
    ReconciliationSettings,
    SchedulerSettings,
    StreamFilterSettings,
    TeamFilterSettings,
)
from .update import (
    increment_epg_generation_counter,
    update_channel_numbering_settings,
    update_dispatcharr_settings,
    update_display_settings,
    update_duration_settings,
    update_epg_settings,
    update_lifecycle_settings,
    update_reconciliation_settings,
    update_scheduler_settings,
    update_team_filter_settings,
)

__all__ = [
    # Types
    "DispatcharrSettings",
    "LifecycleSettings",
    "ReconciliationSettings",
    "SchedulerSettings",
    "EPGSettings",
    "DurationSettings",
    "DisplaySettings",
    "APISettings",
    "StreamFilterSettings",
    "TeamFilterSettings",
    "ChannelNumberingSettings",
    "AllSettings",
    # Read operations
    "get_all_settings",
    "get_dispatcharr_settings",
    "get_scheduler_settings",
    "get_lifecycle_settings",
    "get_epg_settings",
    "get_display_settings",
    "get_stream_filter_settings",
    "get_team_filter_settings",
    "get_channel_numbering_settings",
    # Update operations
    "update_dispatcharr_settings",
    "update_scheduler_settings",
    "update_lifecycle_settings",
    "update_epg_settings",
    "update_reconciliation_settings",
    "update_duration_settings",
    "update_display_settings",
    "update_team_filter_settings",
    "update_channel_numbering_settings",
    "increment_epg_generation_counter",
]
