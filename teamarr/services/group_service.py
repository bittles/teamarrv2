"""Event group processing service facade.

This module provides a clean API for event group processing operations.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class StreamStats:
    """Stream statistics from group processing."""

    fetched: int = 0
    after_filter: int = 0
    filtered_include: int = 0
    filtered_exclude: int = 0
    matched: int = 0
    unmatched: int = 0


@dataclass
class ChannelStats:
    """Channel statistics from group processing."""

    created: int = 0
    existing: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: int = 0


@dataclass
class EPGStats:
    """EPG statistics from group processing."""

    programmes: int = 0
    xmltv_bytes: int = 0


@dataclass
class GroupProcessingResult:
    """Result of processing a single event group."""

    group_id: int
    group_name: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    streams: StreamStats = field(default_factory=StreamStats)
    channels: ChannelStats = field(default_factory=ChannelStats)
    epg: EPGStats = field(default_factory=EPGStats)
    errors: list[str] = field(default_factory=list)


@dataclass
class BatchGroupResult:
    """Result of processing multiple event groups."""

    started_at: datetime | None = None
    completed_at: datetime | None = None
    groups_processed: int = 0
    total_channels_created: int = 0
    total_programmes: int = 0
    total_errors: int = 0
    results: list[GroupProcessingResult] = field(default_factory=list)
    total_xmltv: str = ""


class GroupService:
    """Service for event group processing operations.

    Wraps the consumer layer EventGroupProcessor.
    """

    def __init__(
        self,
        db_factory: Callable[[], Any],
        dispatcharr_client: Any | None = None,
    ):
        """Initialize with database factory and optional Dispatcharr client."""
        self._db_factory = db_factory
        self._client = dispatcharr_client

    def process_group(
        self,
        group_id: int,
        target_date: date | None = None,
    ) -> GroupProcessingResult:
        """Process a single event group.

        Args:
            group_id: Group ID to process
            target_date: Target date (defaults to today)

        Returns:
            GroupProcessingResult with all details
        """
        from teamarr.consumers.event_group_processor import process_event_group

        result = process_event_group(
            db_factory=self._db_factory,
            group_id=group_id,
            dispatcharr_client=self._client,
            target_date=target_date,
        )

        return self._convert_result(result)

    def process_all_groups(
        self,
        target_date: date | None = None,
    ) -> BatchGroupResult:
        """Process all active event groups.

        Args:
            target_date: Target date (defaults to today)

        Returns:
            BatchGroupResult with all group results
        """
        from teamarr.consumers.event_group_processor import process_all_event_groups

        batch = process_all_event_groups(
            db_factory=self._db_factory,
            dispatcharr_client=self._client,
            target_date=target_date,
        )

        return BatchGroupResult(
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            groups_processed=batch.groups_processed,
            total_channels_created=batch.total_channels_created,
            total_programmes=sum(r.programmes_generated for r in batch.results),
            total_errors=batch.total_errors,
            results=[self._convert_result(r) for r in batch.results],
            total_xmltv=batch.total_xmltv,
        )

    def _convert_result(self, result: Any) -> GroupProcessingResult:
        """Convert consumer layer result to service layer result."""
        return GroupProcessingResult(
            group_id=result.group_id,
            group_name=result.group_name,
            started_at=result.started_at,
            completed_at=result.completed_at,
            streams=StreamStats(
                fetched=result.streams_fetched,
                after_filter=result.streams_after_filter,
                filtered_include=result.filtered_include_regex,
                filtered_exclude=result.filtered_exclude_regex,
                matched=result.streams_matched,
                unmatched=result.streams_unmatched,
            ),
            channels=ChannelStats(
                created=result.channels_created,
                existing=result.channels_existing,
                skipped=result.channels_skipped,
                deleted=result.channels_deleted,
                errors=result.channel_errors,
            ),
            epg=EPGStats(
                programmes=result.programmes_generated,
                xmltv_bytes=result.xmltv_size,
            ),
            errors=result.errors,
        )


def create_group_service(
    db_factory: Callable[[], Any],
    dispatcharr_client: Any | None = None,
) -> GroupService:
    """Factory function to create group service."""
    return GroupService(db_factory, dispatcharr_client)
