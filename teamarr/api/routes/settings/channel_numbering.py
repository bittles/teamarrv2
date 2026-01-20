"""Channel numbering settings endpoints."""

from fastapi import APIRouter, HTTPException, status

from teamarr.database import get_db

from .models import (
    ChannelNumberingSettingsModel,
    ChannelNumberingSettingsUpdate,
)

router = APIRouter()

# Valid values for validation
VALID_NUMBERING_MODES = {"strict_block", "rational_block", "strict_compact"}
VALID_SORTING_SCOPES = {"per_group", "global"}
VALID_SORT_BY = {"sport_league_time", "time", "stream_order"}


@router.get("/settings/channel-numbering", response_model=ChannelNumberingSettingsModel)
def get_channel_numbering_settings():
    """Get channel numbering and sorting settings."""
    from teamarr.database.settings import get_channel_numbering_settings

    with get_db() as conn:
        settings = get_channel_numbering_settings(conn)

    return ChannelNumberingSettingsModel(
        numbering_mode=settings.numbering_mode,
        sorting_scope=settings.sorting_scope,
        sort_by=settings.sort_by,
    )


@router.put("/settings/channel-numbering", response_model=ChannelNumberingSettingsModel)
def update_channel_numbering_settings(update: ChannelNumberingSettingsUpdate):
    """Update channel numbering and sorting settings.

    Changes to numbering mode or sorting scope may trigger channel renumbering
    on the next EPG generation.
    """
    from teamarr.database.settings import (
        get_channel_numbering_settings,
        update_channel_numbering_settings,
    )

    # Validate numbering_mode
    if update.numbering_mode is not None:
        if update.numbering_mode not in VALID_NUMBERING_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid numbering_mode. Valid: {VALID_NUMBERING_MODES}",
            )

    # Validate sorting_scope
    if update.sorting_scope is not None:
        if update.sorting_scope not in VALID_SORTING_SCOPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sorting_scope. Valid: {VALID_SORTING_SCOPES}",
            )

    # Validate sort_by
    if update.sort_by is not None:
        if update.sort_by not in VALID_SORT_BY:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort_by. Valid: {VALID_SORT_BY}",
            )

    with get_db() as conn:
        update_channel_numbering_settings(
            conn,
            numbering_mode=update.numbering_mode,
            sorting_scope=update.sorting_scope,
            sort_by=update.sort_by,
        )

    # Return updated settings
    with get_db() as conn:
        settings = get_channel_numbering_settings(conn)

    return ChannelNumberingSettingsModel(
        numbering_mode=settings.numbering_mode,
        sorting_scope=settings.sorting_scope,
        sort_by=settings.sort_by,
    )
