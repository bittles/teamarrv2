"""EPG generation service facade.

This module provides a clean API for EPG generation, hiding the consumer layer
implementation details from the API layer.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from teamarr.services.sports_data import SportsDataService


@dataclass
class TeamChannelConfig:
    """Configuration for a team-based EPG channel."""

    team_id: str
    league: str
    team_name: str
    channel_id: str
    team_abbrev: str | None = None
    logo_url: str | None = None
    title_format: str | None = None
    subtitle_format: str | None = None
    category: str | None = None
    template_id: int | None = None
    additional_leagues: list[str] = field(default_factory=list)


@dataclass
class TeamEPGOptions:
    """Options for team-based EPG generation."""

    schedule_days_ahead: int = 30
    output_days_ahead: int = 14
    sport_durations: dict[str, float] = field(default_factory=dict)
    default_duration_hours: float = 3.0


@dataclass
class EventEPGOptions:
    """Options for event-based EPG generation."""

    output_days_ahead: int = 14
    include_filler: bool = True
    pregame_minutes: int = 0
    postgame_minutes: int = 0


@dataclass
class GenerationResult:
    """Result of EPG generation."""

    programmes: list
    xmltv: str
    teams_processed: int = 0
    events_processed: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EPGService:
    """Service for EPG generation operations.

    This service wraps the consumer layer Orchestrator and provides a clean
    interface for the API layer.
    """

    def __init__(self, sports_service: SportsDataService):
        """Initialize with sports data service."""
        self._service = sports_service

    def generate_team_epg(
        self,
        configs: list[TeamChannelConfig],
        options: TeamEPGOptions | None = None,
    ) -> GenerationResult:
        """Generate EPG for team-based channels.

        Args:
            configs: List of team channel configurations
            options: Generation options (uses defaults if not provided)

        Returns:
            GenerationResult with programmes and XMLTV
        """
        # Import consumer layer here to maintain layer separation
        from teamarr.consumers.orchestrator import Orchestrator
        from teamarr.consumers.orchestrator import TeamChannelConfig as ConsumerConfig
        from teamarr.consumers.team_epg import TeamEPGOptions as ConsumerOptions

        orchestrator = Orchestrator(self._service)

        # Convert service layer types to consumer layer types
        consumer_configs = [
            ConsumerConfig(
                team_id=c.team_id,
                league=c.league,
                team_name=c.team_name,
                channel_id=c.channel_id,
                team_abbrev=c.team_abbrev,
                logo_url=c.logo_url,
                title_format=c.title_format,
                subtitle_format=c.subtitle_format,
                category=c.category,
                template_id=c.template_id,
                additional_leagues=c.additional_leagues,
            )
            for c in configs
        ]

        consumer_options = None
        if options:
            consumer_options = ConsumerOptions(
                schedule_days_ahead=options.schedule_days_ahead,
                output_days_ahead=options.output_days_ahead,
                sport_durations=options.sport_durations,
                default_duration_hours=options.default_duration_hours,
            )

        result = orchestrator.generate_for_teams(consumer_configs, consumer_options)

        return GenerationResult(
            programmes=result.programmes,
            xmltv=result.xmltv,
            teams_processed=result.teams_processed,
            events_processed=0,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )

    def generate_event_epg(
        self,
        leagues: list[str],
        target_date: date,
        channel_prefix: str = "event",
        options: EventEPGOptions | None = None,
    ) -> GenerationResult:
        """Generate EPG for event-based channels.

        Args:
            leagues: List of league codes to generate for
            target_date: Date to generate events for
            channel_prefix: Prefix for channel IDs
            options: Generation options

        Returns:
            GenerationResult with programmes and XMLTV
        """
        from teamarr.consumers.event_epg import EventEPGOptions as ConsumerOptions
        from teamarr.consumers.orchestrator import Orchestrator

        orchestrator = Orchestrator(self._service)

        consumer_options = None
        if options:
            consumer_options = ConsumerOptions(
                output_days_ahead=options.output_days_ahead,
            )

        result = orchestrator.generate_for_events(
            leagues=leagues,
            target_date=target_date,
            channel_prefix=channel_prefix,
            options=consumer_options,
        )

        return GenerationResult(
            programmes=result.programmes,
            xmltv=result.xmltv,
            teams_processed=0,
            events_processed=result.events_processed,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )


def create_epg_service(sports_service: SportsDataService) -> EPGService:
    """Factory function to create EPG service."""
    return EPGService(sports_service)
