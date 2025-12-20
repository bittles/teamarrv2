"""Event matching service facade.

This module provides a clean API for event matching operations.
"""

from dataclasses import dataclass
from datetime import date

from teamarr.core.types import Event
from teamarr.services.sports_data import SportsDataService


@dataclass
class MatchResult:
    """Result of event matching."""

    found: bool
    event: Event | None = None


class MatchingService:
    """Service for event matching operations.

    Wraps the consumer layer EventMatcher and provides a clean interface.
    """

    def __init__(self, sports_service: SportsDataService):
        """Initialize with sports data service."""
        self._service = sports_service

    def match_by_team_ids(
        self,
        league: str,
        target_date: date,
        team1_id: str,
        team2_id: str,
    ) -> MatchResult:
        """Match event by team IDs.

        Args:
            league: League code
            target_date: Date to search
            team1_id: First team's provider ID
            team2_id: Second team's provider ID

        Returns:
            MatchResult with found status and event if matched
        """
        from teamarr.consumers.event_matcher import EventMatcher

        events = self._service.get_events(league, target_date)
        if not events:
            return MatchResult(found=False)

        matcher = EventMatcher()
        event = matcher.find_by_team_ids(events, team1_id, team2_id)

        if event:
            return MatchResult(found=True, event=event)
        return MatchResult(found=False)

    def match_by_team_names(
        self,
        league: str,
        target_date: date,
        team1_name: str,
        team2_name: str,
    ) -> MatchResult:
        """Match event by team names.

        Args:
            league: League code
            target_date: Date to search
            team1_name: First team's name (fuzzy matched)
            team2_name: Second team's name (fuzzy matched)

        Returns:
            MatchResult with found status and event if matched
        """
        from teamarr.consumers.event_matcher import EventMatcher

        events = self._service.get_events(league, target_date)
        if not events:
            return MatchResult(found=False)

        matcher = EventMatcher()
        event = matcher.find_by_team_names(events, team1_name, team2_name)

        if event:
            return MatchResult(found=True, event=event)
        return MatchResult(found=False)


def create_matching_service(sports_service: SportsDataService) -> MatchingService:
    """Factory function to create matching service."""
    return MatchingService(sports_service)
