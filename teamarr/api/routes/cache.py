"""Team and league cache API endpoints.

Provides endpoints for cache management:
- GET /cache/status - Get cache statistics
- POST /cache/refresh - Trigger cache refresh (SSE streaming)
- GET /cache/refresh/status - Get refresh progress
- GET /cache/leagues - List cached leagues
- GET /cache/teams/search - Search teams by name
- GET /cache/candidate-leagues - Find candidate leagues for a matchup
"""

import json
import logging
import queue
import threading

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from teamarr.api.cache_refresh_status import (
    complete_refresh,
    fail_refresh,
    get_refresh_status,
    is_refresh_in_progress,
    start_refresh,
    update_refresh_status,
)
from teamarr.database import get_db
from teamarr.services import create_cache_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache")


@router.get("/status")
def get_cache_status() -> dict:
    """Get cache statistics and status.

    Returns:
        Cache status including last refresh time, counts, and staleness
    """
    cache_service = create_cache_service(get_db)
    stats = cache_service.get_stats()

    return {
        "last_refresh": stats.last_refresh.isoformat() if stats.last_refresh else None,
        "leagues_count": stats.leagues_count,
        "teams_count": stats.teams_count,
        "refresh_duration_seconds": stats.refresh_duration_seconds,
        "is_stale": stats.is_stale,
        "is_empty": stats.is_empty,
        "refresh_in_progress": stats.refresh_in_progress,
        "last_error": stats.last_error,
    }


@router.get("/refresh/status")
def get_refresh_progress() -> dict:
    """Get current cache refresh progress.

    Returns:
        Current refresh status including percent, message, phase
    """
    return get_refresh_status()


@router.post("/refresh")
def trigger_refresh():
    """Trigger a cache refresh from all providers with SSE progress streaming.

    Streams real-time progress updates via Server-Sent Events.
    Frontend should connect with EventSource to receive updates.

    Returns:
        SSE stream with progress updates
    """
    # Check if already in progress
    if is_refresh_in_progress():
        err = {"status": "error", "message": "Cache refresh already in progress"}
        return StreamingResponse(
            iter([f"data: {json.dumps(err)}\n\n"]),
            media_type="text/event-stream",
        )

    # Mark as started
    if not start_refresh():
        err = {"status": "error", "message": "Failed to start cache refresh"}
        return StreamingResponse(
            iter([f"data: {json.dumps(err)}\n\n"]),
            media_type="text/event-stream",
        )

    # Queue for progress updates
    progress_queue: queue.Queue = queue.Queue()

    def generate():
        """Generator function for SSE stream."""

        def run_refresh():
            """Run cache refresh in background thread."""
            try:
                svc = create_cache_service(get_db)

                # Progress callback that updates status and queues for SSE
                def progress_callback(message: str, percent: int) -> None:
                    update_refresh_status(
                        status="progress",
                        message=message,
                        percent=percent,
                    )
                    progress_queue.put(get_refresh_status())

                result = svc.refresh(progress_callback=progress_callback)

                if result.success:
                    complete_refresh(
                        {
                            "success": True,
                            "leagues_count": result.leagues_added,
                            "teams_count": result.teams_added,
                            "duration_seconds": result.duration_seconds,
                        }
                    )
                else:
                    fail_refresh("; ".join(result.errors) if result.errors else "Unknown error")

                progress_queue.put(get_refresh_status())

            except Exception as e:
                logger.exception("Cache refresh failed")
                fail_refresh(str(e))
                progress_queue.put(get_refresh_status())

            finally:
                progress_queue.put({"_done": True})

        # Start refresh thread
        refresh_thread = threading.Thread(target=run_refresh, daemon=True)
        refresh_thread.start()

        # Stream progress updates
        while True:
            try:
                data = progress_queue.get(timeout=0.5)

                if data.get("_done"):
                    break

                yield f"data: {json.dumps(data)}\n\n"

            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"

        # Wait for thread to complete
        refresh_thread.join(timeout=5)

        # Send final status
        yield f"data: {json.dumps(get_refresh_status())}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sports")
def list_sports() -> dict:
    """Get all sport codes and their display names.

    Returns:
        Dict mapping sport codes to display names
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sport_code, display_name FROM sports ORDER BY display_name")
        sports = {row["sport_code"]: row["display_name"] for row in cursor.fetchall()}

    return {"sports": sports}


@router.get("/leagues")
def list_leagues(
    sport: str | None = Query(None, description="Filter by sport (e.g., 'soccer')"),
    provider: str | None = Query(None, description="Filter by provider"),
    import_only: bool = Query(False, description="Only import-enabled leagues"),
) -> dict:
    """List all available leagues.

    By default, returns all leagues (configured + discovered).
    Use import_only=True for Team Importer to get only explicitly configured
    leagues with import_enabled=1.

    Args:
        sport: Optional sport filter
        provider: Optional provider filter
        import_only: If True, only return import-enabled configured leagues

    Returns:
        List of leagues
    """
    cache_service = create_cache_service(get_db)
    leagues = cache_service.get_leagues(
        sport=sport, provider=provider, import_enabled_only=import_only
    )

    return {
        "count": len(leagues),
        "leagues": [
            {
                "slug": league.slug,
                "provider": league.provider,
                "name": league.name,
                "sport": league.sport,
                "team_count": league.team_count,
                "logo_url": league.logo_url,
                "logo_url_dark": league.logo_url_dark,
                "import_enabled": league.import_enabled,
                "league_alias": league.league_alias,
            }
            for league in leagues
        ],
    }


@router.get("/teams/search")
def search_teams(
    q: str = Query(..., min_length=2, description="Search query (team name)"),
    league: str | None = Query(None, description="Filter by league slug"),
    sport: str | None = Query(None, description="Filter by sport"),
) -> dict:
    """Search for teams in the cache.

    Args:
        q: Search query (partial match on team name)
        league: Optional league filter
        sport: Optional sport filter

    Returns:
        Matching teams
    """
    q_lower = q.lower().strip()

    with get_db() as conn:
        cursor = conn.cursor()

        query = """
            SELECT team_name, team_abbrev, team_short_name, provider,
                   provider_team_id, league, sport, logo_url
            FROM team_cache
            WHERE (LOWER(team_name) LIKE ?
                   OR LOWER(team_abbrev) = ?
                   OR LOWER(team_short_name) LIKE ?)
        """
        params: list = [f"%{q_lower}%", q_lower, f"%{q_lower}%"]

        if league:
            query += " AND league = ?"
            params.append(league)
        if sport:
            query += " AND sport = ?"
            params.append(sport)

        query += " ORDER BY team_name LIMIT 50"

        cursor.execute(query, params)

        teams = [
            {
                "name": row["team_name"],
                "abbrev": row["team_abbrev"],
                "short_name": row["team_short_name"],
                "provider": row["provider"],
                "team_id": row["provider_team_id"],
                "league": row["league"],
                "sport": row["sport"],
                "logo_url": row["logo_url"],
            }
            for row in cursor.fetchall()
        ]

    return {
        "query": q,
        "count": len(teams),
        "teams": teams,
    }


@router.get("/candidate-leagues")
def find_candidate_leagues(
    team1: str = Query(..., min_length=2, description="First team name"),
    team2: str = Query(..., min_length=2, description="Second team name"),
    sport: str | None = Query(None, description="Filter by sport"),
) -> dict:
    """Find leagues where both teams exist.

    Used for event matching - given two team names, find which leagues
    they could both be playing in.

    Args:
        team1: First team name
        team2: Second team name
        sport: Optional sport filter

    Returns:
        List of (league, provider) tuples where both teams exist
    """
    cache_service = create_cache_service(get_db)
    candidates = cache_service.find_candidate_leagues(team1, team2, sport)

    return {
        "team1": team1,
        "team2": team2,
        "candidates": [{"league": league, "provider": provider} for league, provider in candidates],
        "count": len(candidates),
    }


@router.get("/leagues/{league_slug}/teams")
def get_league_teams(league_slug: str) -> list[dict]:
    """Get all teams for a specific league.

    Args:
        league_slug: League identifier (e.g., 'nfl', 'eng.1')

    Returns:
        List of teams in the league
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, team_name, team_abbrev, team_short_name, provider,
                   provider_team_id, league, sport, logo_url
            FROM team_cache
            WHERE league = ?
            ORDER BY team_name
            """,
            (league_slug,),
        )

        return [
            {
                "id": row["id"],
                "team_name": row["team_name"],
                "team_abbrev": row["team_abbrev"],
                "team_short_name": row["team_short_name"],
                "provider": row["provider"],
                "provider_team_id": row["provider_team_id"],
                "league": row["league"],
                "sport": row["sport"],
                "logo_url": row["logo_url"],
            }
            for row in cursor.fetchall()
        ]


@router.get("/team-leagues/{provider}/{provider_team_id}")
def get_team_leagues(provider: str, provider_team_id: str) -> dict:
    """Get all leagues a team plays in.

    Used for multi-league display (e.g., soccer teams playing in
    domestic league, Champions League, cup competitions, etc.)

    Args:
        provider: Provider name ('espn' or 'tsdb')
        provider_team_id: Team ID from the provider

    Returns:
        Dict with team info and list of leagues
    """
    # Query leagues directly from database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT league
            FROM team_cache
            WHERE provider = ? AND provider_team_id = ?
            """,
            (provider, provider_team_id),
        )
        leagues = [row["league"] for row in cursor.fetchall()]

    # Get league details for each
    cache_service = create_cache_service(get_db)
    all_leagues = cache_service.get_leagues()
    league_lookup = {lg.slug: lg for lg in all_leagues}

    league_details = []
    for league_slug in leagues:
        if league_slug in league_lookup:
            entry = league_lookup[league_slug]
            league_details.append(
                {
                    "slug": entry.slug,
                    "name": entry.name,
                    "sport": entry.sport,
                    "logo_url": entry.logo_url,
                }
            )
        else:
            # League not found in cache, add basic info
            league_details.append(
                {
                    "slug": league_slug,
                    "name": league_slug.upper(),
                    "sport": None,
                    "logo_url": None,
                }
            )

    return {
        "provider": provider,
        "provider_team_id": provider_team_id,
        "leagues": league_details,
        "count": len(league_details),
    }


@router.get("/team-picker-leagues")
def get_team_picker_leagues() -> dict:
    """Get all leagues from team_cache for the TeamPicker component.

    Returns unique leagues from team_cache with their sports.
    Leagues that exist in the configured leagues table sort first.
    This endpoint is the source of truth for TeamPicker to avoid
    "unknown sport" issues.

    Returns:
        List of leagues with sport and is_configured flag, plus sport display names
    """
    from teamarr.core.sports import get_sport_display_names_from_db

    with get_db() as conn:
        cursor = conn.cursor()

        # Get sport display names from sports table
        sport_display_names = get_sport_display_names_from_db(conn)

        # Get unique leagues from team_cache (source of truth)
        # LEFT JOIN with leagues table to get is_configured flag and display name
        # Sort: configured first, then by sport, then by league name
        cursor.execute(
            """
            SELECT
                tc.league,
                tc.sport,
                tc.provider,
                COUNT(*) as team_count,
                CASE WHEN l.league_code IS NOT NULL THEN 1 ELSE 0 END as is_configured,
                COALESCE(l.display_name, lc.league_name, UPPER(tc.league)) as display_name,
                l.logo_url as configured_logo_url,
                lc.logo_url as cached_logo_url
            FROM team_cache tc
            LEFT JOIN leagues l ON l.league_code = tc.league
            LEFT JOIN league_cache lc ON lc.league_slug = tc.league
            GROUP BY tc.league, tc.sport, tc.provider
            ORDER BY
                is_configured DESC,
                tc.sport,
                display_name
            """
        )

        leagues = [
            {
                "slug": row["league"],
                "sport": row["sport"],
                "sport_display_name": sport_display_names.get(row["sport"], row["sport"].title()),
                "provider": row["provider"],
                "team_count": row["team_count"],
                "is_configured": bool(row["is_configured"]),
                "name": row["display_name"],
                "logo_url": row["configured_logo_url"] or row["cached_logo_url"],
            }
            for row in cursor.fetchall()
        ]

    return {
        "count": len(leagues),
        "leagues": leagues,
    }


@router.get("/league/{league_slug}")
def get_league_info(league_slug: str) -> dict:
    """Get info for a specific league.

    Args:
        league_slug: League identifier (e.g., 'nfl', 'eng.1')

    Returns:
        League metadata or 404
    """
    # Query directly from database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT league, provider, sport, COUNT(*) as team_count
            FROM team_cache
            WHERE league = ?
            GROUP BY league, provider, sport
            """,
            (league_slug,),
        )
        row = cursor.fetchone()

    if not row:
        return {"error": "League not found", "league": league_slug}

    # Get league name from league_cache if available
    league_name = league_slug.upper()
    with get_db() as conn:
        name_row = conn.execute(
            "SELECT league_name FROM league_cache WHERE league_slug = ?",
            (league_slug,),
        ).fetchone()
        if name_row:
            league_name = name_row["league_name"]

    return {
        "slug": row["league"],
        "provider": row["provider"],
        "name": league_name,
        "sport": row["sport"],
        "team_count": row["team_count"],
    }
