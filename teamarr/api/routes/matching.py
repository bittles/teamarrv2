"""Event matching endpoints."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from teamarr.api.dependencies import get_sports_service
from teamarr.api.models import EventMatchRequest, EventMatchResponse
from teamarr.services import SportsDataService, create_matching_service

router = APIRouter()


def _parse_date(date_str: str | None) -> date:
    """Parse date string or return today."""
    if not date_str:
        return date.today()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD.",
        ) from None


@router.post("/matching/events", response_model=EventMatchResponse)
def match_event(
    request: EventMatchRequest,
    service: SportsDataService = Depends(get_sports_service),
):
    """Match a query to a sporting event."""
    target = _parse_date(request.target_date)
    matching_service = create_matching_service(service)

    if request.team1_id and request.team2_id:
        result = matching_service.match_by_team_ids(
            request.league, target, request.team1_id, request.team2_id
        )
    elif request.team1_name and request.team2_name:
        result = matching_service.match_by_team_names(
            request.league, target, request.team1_name, request.team2_name
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either (team1_id, team2_id) or (team1_name, team2_name)",
        )

    if not result.found or not result.event:
        return EventMatchResponse(found=False)

    return EventMatchResponse(
        found=True,
        event_id=result.event.id,
        event_name=result.event.name,
        home_team=result.event.home_team.name,
        away_team=result.event.away_team.name,
        start_time=result.event.start_time.isoformat(),
        venue=result.event.venue.name if result.event.venue else None,
    )
