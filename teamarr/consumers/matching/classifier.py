"""Stream classification for matching strategy selection.

Classifies streams into categories that determine which matching
strategy to use:
- TEAM_VS_TEAM: Standard team sports (NFL, NBA, Soccer, etc.)
- EVENT_CARD: Combat sports with event cards (UFC, Boxing)
- PLACEHOLDER: Filler streams with no event info (skip)
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from re import Pattern

from teamarr.consumers.matching.normalizer import NormalizedStream, normalize_stream
from teamarr.utilities.constants import (
    EVENT_CARD_KEYWORDS,
    GAME_SEPARATORS,
    LEAGUE_HINT_PATTERNS,
    PLACEHOLDER_PATTERNS,
    SPORT_HINT_PATTERNS,
)

logger = logging.getLogger(__name__)


class StreamCategory(Enum):
    """Stream category for matching strategy selection."""

    TEAM_VS_TEAM = "team_vs_team"  # Standard team matchup (vs/@/at)
    EVENT_CARD = "event_card"  # Combat sports (UFC, Boxing)
    PLACEHOLDER = "placeholder"  # No event info, skip


@dataclass
class ClassifiedStream:
    """Result of stream classification with extracted components."""

    category: StreamCategory
    normalized: NormalizedStream

    # For TEAM_VS_TEAM: extracted team names
    team1: str | None = None
    team2: str | None = None
    separator_found: str | None = None

    # For EVENT_CARD: event hint (e.g., "UFC 315")
    event_hint: str | None = None

    # Detected league hint (for any category)
    league_hint: str | None = None

    # Detected sport hint (e.g., "Hockey", "Football")
    sport_hint: str | None = None

    # Track if custom regex was used
    custom_regex_used: bool = False


@dataclass
class CustomRegexConfig:
    """Configuration for custom regex extraction (teams, date, time)."""

    teams_pattern: str | None = None
    teams_enabled: bool = False
    date_pattern: str | None = None
    date_enabled: bool = False
    time_pattern: str | None = None
    time_enabled: bool = False

    # Compiled patterns (cached)
    _compiled_teams: Pattern | None = None
    _compiled_date: Pattern | None = None
    _compiled_time: Pattern | None = None

    def get_pattern(self) -> Pattern | None:
        """Get compiled teams regex pattern, compiling on first access."""
        if not self.teams_enabled or not self.teams_pattern:
            return None

        if self._compiled_teams is None:
            try:
                self._compiled_teams = re.compile(self.teams_pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning("[CLASSIFY] Invalid custom teams regex pattern: %s", e)
                return None

        return self._compiled_teams

    def get_date_pattern(self) -> Pattern | None:
        """Get compiled date regex pattern, compiling on first access."""
        if not self.date_enabled or not self.date_pattern:
            return None

        if self._compiled_date is None:
            try:
                self._compiled_date = re.compile(self.date_pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning("[CLASSIFY] Invalid custom date regex pattern: %s", e)
                return None

        return self._compiled_date

    def get_time_pattern(self) -> Pattern | None:
        """Get compiled time regex pattern, compiling on first access."""
        if not self.time_enabled or not self.time_pattern:
            return None

        if self._compiled_time is None:
            try:
                self._compiled_time = re.compile(self.time_pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning("[CLASSIFY] Invalid custom time regex pattern: %s", e)
                return None

        return self._compiled_time


def extract_teams_with_custom_regex(
    text: str,
    config: CustomRegexConfig,
) -> tuple[str | None, str | None, bool]:
    """Extract team names using custom regex pattern.

    Args:
        text: Stream name (normalized)
        config: Custom regex configuration

    Returns:
        Tuple of (team1, team2, success)
    """
    pattern = config.get_pattern()
    if not pattern:
        return None, None, False

    match = pattern.search(text)
    if not match:
        return None, None, False

    # Try numbered groups first (group 1 and 2)
    groups = match.groups()
    if len(groups) >= 2:
        team1 = groups[0].strip() if groups[0] else None
        team2 = groups[1].strip() if groups[1] else None
        if team1 and team2:
            return team1, team2, True

    # Try named groups (?P<team1>...) and (?P<team2>...)
    try:
        team1 = match.group("team1")
        team2 = match.group("team2")
        if team1 and team2:
            return team1.strip(), team2.strip(), True
    except (IndexError, re.error):
        pass

    return None, None, False


def extract_date_with_custom_regex(
    text: str,
    config: CustomRegexConfig,
) -> date | None:
    """Extract date using custom regex pattern.

    Supports:
    - Named group: (?P<date>...) - returns raw string to parse
    - Named groups: (?P<month>...) (?P<day>...) (?P<year>...) - combines
    - Single capture group - returns raw string to parse

    Args:
        text: Stream name (original, not normalized)
        config: Custom regex configuration

    Returns:
        Extracted date or None
    """
    from datetime import datetime

    pattern = config.get_date_pattern()
    if not pattern:
        return None

    match = pattern.search(text)
    if not match:
        return None

    try:
        # Try named group 'date' first (full date string)
        try:
            date_str = match.group("date")
            if date_str:
                return _parse_date_string(date_str.strip())
        except (IndexError, re.error):
            pass

        # Try individual named groups (month, day, year)
        try:
            month_str = match.group("month")
            day_str = match.group("day")
            if month_str and day_str:
                month = _parse_month(month_str.strip())
                day = int(day_str.strip())
                try:
                    year = int(match.group("year").strip())
                    if year < 100:
                        year += 2000 if year < 50 else 1900
                except (IndexError, re.error, ValueError, AttributeError):
                    year = datetime.now().year
                return date(year, month, day)
        except (IndexError, re.error, ValueError, AttributeError):
            pass

        # Try first capture group as raw date string
        groups = match.groups()
        if groups and groups[0]:
            return _parse_date_string(groups[0].strip())

    except (ValueError, TypeError) as e:
        logger.debug("[CLASSIFY] Failed to parse custom date: %s", e)

    return None


def _parse_month(month_str: str) -> int:
    """Parse month from string (name or number)."""
    month_names = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    month_lower = month_str.lower()
    if month_lower in month_names:
        return month_names[month_lower]
    return int(month_str)


def _parse_date_string(date_str: str) -> date | None:
    """Parse various date string formats."""
    from datetime import datetime

    # Common formats to try
    formats = [
        "%d %b",      # 14 Jan
        "%d %B",      # 14 January
        "%b %d",      # Jan 14
        "%B %d",      # January 14
        "%m/%d/%Y",   # 01/14/2026
        "%m/%d/%y",   # 01/14/26
        "%d/%m/%Y",   # 14/01/2026
        "%d/%m/%y",   # 14/01/26
        "%Y-%m-%d",   # 2026-01-14
        "%d-%m-%Y",   # 14-01-2026
    ]

    # Clean up ordinal suffixes (1st, 2nd, 3rd, 4th)
    date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            # If no year in format, use current year
            if "%Y" not in fmt and "%y" not in fmt:
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.date()
        except ValueError:
            continue

    return None


def extract_time_with_custom_regex(
    text: str,
    config: CustomRegexConfig,
) -> time | None:
    """Extract time using custom regex pattern.

    Supports:
    - Named group: (?P<time>...) - returns raw string to parse
    - Named groups: (?P<hour>...) (?P<minute>...) (?P<ampm>...) - combines
    - Single capture group - returns raw string to parse

    Args:
        text: Stream name (original, not normalized)
        config: Custom regex configuration

    Returns:
        Extracted time or None
    """
    pattern = config.get_time_pattern()
    if not pattern:
        return None

    match = pattern.search(text)
    if not match:
        return None

    try:
        # Try named group 'time' first (full time string)
        try:
            time_str = match.group("time")
            if time_str:
                return _parse_time_string(time_str.strip())
        except (IndexError, re.error):
            pass

        # Try individual named groups (hour, minute, ampm)
        try:
            hour = int(match.group("hour").strip())
            try:
                minute = int(match.group("minute").strip())
            except (IndexError, re.error, ValueError, AttributeError):
                minute = 0

            try:
                ampm = match.group("ampm").strip().upper()
                if ampm == "PM" and hour < 12:
                    hour += 12
                elif ampm == "AM" and hour == 12:
                    hour = 0
            except (IndexError, re.error, ValueError, AttributeError):
                pass

            return time(hour, minute)
        except (IndexError, re.error, ValueError, AttributeError):
            pass

        # Try first capture group as raw time string
        groups = match.groups()
        if groups and groups[0]:
            return _parse_time_string(groups[0].strip())

    except (ValueError, TypeError) as e:
        logger.debug("[CLASSIFY] Failed to parse custom time: %s", e)

    return None


def _parse_time_string(time_str: str) -> time | None:
    """Parse various time string formats."""
    from datetime import datetime

    # Common formats to try
    formats = [
        "%I:%M%p",    # 6:45pm
        "%I:%M %p",   # 6:45 pm
        "%I%p",       # 6pm
        "%I %p",      # 6 pm
        "%H:%M",      # 18:45
        "%H%M",       # 1845
    ]

    # Normalize: remove spaces between number and am/pm
    time_str_normalized = re.sub(r"(\d+)\s*(am|pm)", r"\1\2", time_str, flags=re.IGNORECASE)

    for fmt in formats:
        try:
            parsed = datetime.strptime(time_str_normalized, fmt)
            return parsed.time()
        except ValueError:
            continue

    # Also try the original string
    if time_str != time_str_normalized:
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                return parsed.time()
            except ValueError:
                continue

    return None


# =============================================================================
# PLACEHOLDER DETECTION
# =============================================================================


def is_placeholder(text: str) -> bool:
    """Check if stream name matches placeholder patterns.

    Placeholders are filler streams with no real event info,
    like "ESPN+ 45" or "Coming Soon".

    Args:
        text: Normalized stream name

    Returns:
        True if stream is a placeholder
    """
    if not text:
        return True

    text_lower = text.lower().strip()

    # Check against placeholder patterns
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    # Additional check: very short names with just numbers
    if re.match(r"^[\d\s\-:]+$", text_lower):
        return True

    return False


# =============================================================================
# GAME SEPARATOR DETECTION
# =============================================================================


def find_game_separator(text: str) -> tuple[str | None, int]:
    """Find game separator in stream name.

    Args:
        text: Stream name (should be normalized)

    Returns:
        Tuple of (separator found, position) or (None, -1)
    """
    if not text:
        return None, -1

    text_lower = text.lower()

    for sep in GAME_SEPARATORS:
        pos = text_lower.find(sep.lower())
        if pos != -1:
            return sep, pos

    return None, -1


def extract_teams_from_separator(
    text: str, separator: str, sep_position: int
) -> tuple[str | None, str | None]:
    """Extract team names from a stream with a separator.

    Args:
        text: Stream name
        separator: The separator found (e.g., " vs ")
        sep_position: Position of separator in text

    Returns:
        Tuple of (team1, team2)
    """
    if sep_position < 0:
        return None, None

    team1 = text[:sep_position].strip()
    team2 = text[sep_position + len(separator) :].strip()

    # Clean up teams (remove DATE_MASK, TIME_MASK, trailing punctuation)
    team1 = _clean_team_name(team1)
    team2 = _clean_team_name(team2)

    # Validate: both teams should have substance
    if not team1 or len(team1) < 2:
        team1 = None
    if not team2 or len(team2) < 2:
        team2 = None

    return team1, team2


def _clean_team_name(name: str) -> str:
    """Clean extracted team name."""
    if not name:
        return ""

    # Remove datetime masks and trailing timezone remnants
    name = re.sub(r"\bDATE_MASK\b", "", name)
    name = re.sub(r"\bTIME_MASK\b", "", name)
    # After mask removal, clean up "@ ET", "@ EST", "@ PT", etc.
    name = re.sub(r"\s*@\s*[A-Z]{2,4}T?\s*$", "", name, flags=re.IGNORECASE)

    # Remove leading punctuation ONLY (not digits - team names like 49ers, 76ers start with numbers)
    # Strip whitespace, dashes, colons, periods, commas at the start
    name = re.sub(r"^[\s\-:.,]+", "", name)

    # Remove trailing punctuation (NOT digits - they could be team names like 49ers, 76ers)
    # Only strip trailing separators that shouldn't be part of team names
    name = re.sub(r"[\s\-:.,@]+$", "", name)

    # Remove channel numbers like "(1)" or "[2]"
    name = re.sub(r"\s*[\(\[]\d+[\)\]]\s*$", "", name)

    # Remove HD, SD, etc.
    name = re.sub(r"\s+\b(HD|SD|FHD|4K|UHD)\b\s*$", "", name, flags=re.IGNORECASE)

    # Strip leading channel numbers like "02 :", "15 :", "142 :" (from ESPN+ XX :)
    name = re.sub(r"^\d+\s*:\s*", "", name)

    # Strip numbered channel prefixes like "NFL Game Pass 03:", "ESPN+ 45:", "Sportsnet+ 04:"
    # Pattern: Words (may include +) followed by optional number, then colon
    # This handles "Name Number:" and "Name+ Number:" patterns at the start
    name = re.sub(r"^[A-Za-z][A-Za-z\s+]*\d*:\s*", "", name)

    # Strip round/competition indicators at end of team names
    # Common patterns in cup competitions, playoffs, etc.
    # - (Round 3), (Rd 3), (R3), (Rnd 3), (3rd Round), (Third Round)
    # - (Group A), (Grp A), (Group Stage)
    # - (Matchday 5), (MD 5), (MD5), (Week 10)
    # - (Leg 1), (1st Leg), (2nd Leg), (Leg One)
    # - (Final), (Semi-Final), (Quarter-Final), (QF), (SF), (Semi)
    # - (Playoffs), (Playoff), (Play-off)
    # - (Qualifying), (Qual), (Q1), (Q2)
    round_pattern = r"""
        \s*\(
        (?:
            (?:Round|Rd|Rnd|R)\s*\d+\w*  |  # Round 3, Rd 3, R3
            \d+(?:st|nd|rd|th)?\s*(?:Round|Rd|Leg)  |  # 3rd Round, 1st Leg
            (?:First|Second|Third|Fourth|Fifth)\s*(?:Round|Leg)  |  # Third Round
            (?:Group|Grp|Gr)\s*\w*  |  # Group A, Group Stage
            (?:Matchday|MD|Week|Wk)\s*\d*  |  # Matchday 5, MD5, Week 10
            (?:Leg|Game)\s*(?:One|Two|\d+)  |  # Leg 1, Leg One
            (?:Quarter|Semi|Half)?-?(?:Final|Finals)  |  # Final, Semi-Final
            (?:QF|SF|F)  |  # QF, SF, F
            (?:Play-?off|Play-?offs)  |  # Playoff, Play-off
            (?:Qualifying|Qual|Q)\d*  |  # Qualifying, Q1
            (?:Prelim|Preliminary)  |  # Preliminary
            (?:1H|2H|OT|ET)  |  # 1st half, overtime, extra time markers
            (?:Live|LIVE|Replay|Encore)  # Broadcast markers
        )
        \s*\)
    """
    name = re.sub(round_pattern, "", name, flags=re.IGNORECASE | re.VERBOSE)

    # Handle "|" separator - often used for show description before team names
    # "Manningcast | MNF with Peyton & Eli: Seahawks" → take part after last "|"
    # But only if there's no game separator after the "|" portion
    if "|" in name:
        # Check if the part after the last colon looks like a team name
        parts = name.split("|")
        last_part = parts[-1].strip()
        # If the last part after "|" has a colon with something after it, use that
        if ":" in last_part:
            after_colon = last_part.split(":")[-1].strip()
            if after_colon and len(after_colon) >= 3:
                name = after_colon

    # Strip show name prefixes that precede team names
    # Patterns like "MNF Playbook:", "NFL RedZone:", "Inside the NBA:"
    # Match pattern: "Word Word:" or "Word Word Word:" at the start
    # Must start with capital letter and contain only letters/spaces before colon
    # Apply repeatedly to handle nested prefixes like "Channel: Show: Team"
    prev = None
    while prev != name:
        prev = name
        name = re.sub(r"^[A-Z][A-Za-z\s]+:\s*", "", name)

    return name.strip()


# =============================================================================
# LEAGUE HINT DETECTION
# =============================================================================


def detect_league_hint(text: str) -> str | None:
    """Detect league from stream name patterns.

    Examples:
        "NHL: Bruins vs Rangers" → "nhl"
        "EPL - Arsenal vs Chelsea" → "eng.1"
        "UFC 315: Main Card" → "ufc"

    Args:
        text: Stream name (should be normalized)

    Returns:
        League code if detected, None otherwise
    """
    if not text:
        return None

    text_lower = text.lower()

    for pattern, league_code in LEAGUE_HINT_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return league_code

    return None


def detect_sport_hint(text: str) -> str | None:
    """Detect sport type from stream name.

    Unlike league hints which only match at start of string,
    sport hints can match anywhere (e.g., "Ice Hockey" in the middle).

    Examples:
        "US (BTN+) | Ice Hockey (W): Minnesota at Wisconsin" → "Hockey"
        "ESPN: NFL Sunday Football" → "Football"
        "Basketball: Lakers vs Celtics" → "Basketball"

    Args:
        text: Stream name (should be normalized)

    Returns:
        Sport name matching leagues.sport column if detected, None otherwise
    """
    if not text:
        return None

    text_lower = text.lower()

    for pattern, sport in SPORT_HINT_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return sport

    return None


# =============================================================================
# EVENT CARD DETECTION
# =============================================================================


def is_event_card(text: str, league_event_type: str | None = None) -> bool:
    """Check if stream is an event card (UFC, Boxing).

    Args:
        text: Normalized stream name
        league_event_type: Optional event_type from leagues table

    Returns:
        True if stream is an event card
    """
    if not text:
        return False

    # If we know the league type, use that
    if league_event_type == "event_card":
        return True

    text_lower = text.lower()

    # Check for event card keywords
    for _league, keywords in EVENT_CARD_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return True

    return False


def extract_event_card_hint(text: str) -> str | None:
    """Extract event card identifier (e.g., "UFC 315").

    Args:
        text: Stream name

    Returns:
        Event identifier if found, None otherwise
    """
    if not text:
        return None

    # UFC 315, UFC FN 123, etc.
    ufc_match = re.search(r"\b(ufc\s*(?:fn|fight\s*night)?\s*\d+)\b", text, re.IGNORECASE)
    if ufc_match:
        return ufc_match.group(1).upper().replace("  ", " ")

    # PFL 5, Bellator 300, etc.
    org_match = re.search(r"\b((?:pfl|bellator|one\s*fc)\s*\d+)\b", text, re.IGNORECASE)
    if org_match:
        return org_match.group(1).upper()

    # Boxing event names are less standardized - look for main event patterns
    if any(kw in text.lower() for kw in EVENT_CARD_KEYWORDS.get("boxing", [])):
        # Try to extract fighter names or event name
        # For now, just return a generic hint
        return "BOXING_EVENT"

    return None


# =============================================================================
# MAIN CLASSIFICATION
# =============================================================================


def classify_stream(
    stream_name: str,
    league_event_type: str | None = None,
    custom_regex: CustomRegexConfig | None = None,
) -> ClassifiedStream:
    """Classify a stream for matching strategy selection.

    Classification order:
    1. Normalize stream name
    1b. Apply custom date/time regex (if configured) to override extracted values
    2. Check for placeholder patterns → PLACEHOLDER
    3. Check for event card keywords/type → EVENT_CARD
    4. Try custom regex for team extraction (if configured) → TEAM_VS_TEAM
    5. Check for game separator (vs/@/at) → TEAM_VS_TEAM
    6. Default → PLACEHOLDER (can't classify)

    Args:
        stream_name: Raw stream name from M3U
        league_event_type: Optional event_type from leagues table
        custom_regex: Optional custom regex configuration for extraction

    Returns:
        ClassifiedStream with category and extracted info
    """
    # Step 1: Normalize
    normalized = normalize_stream(stream_name)
    result: ClassifiedStream | None = None

    # Step 1b: Apply custom date/time regex to override built-in extraction
    # Uses ORIGINAL stream name (not normalized) for more flexible matching
    if custom_regex:
        if custom_regex.date_enabled:
            custom_date = extract_date_with_custom_regex(stream_name, custom_regex)
            if custom_date:
                normalized.extracted_date = custom_date
                logger.debug(
                    "[CLASSIFY] Custom date regex extracted: %s from '%s'",
                    custom_date, stream_name[:50]
                )

        if custom_regex.time_enabled:
            custom_time = extract_time_with_custom_regex(stream_name, custom_regex)
            if custom_time:
                normalized.extracted_time = custom_time
                logger.debug(
                    "[CLASSIFY] Custom time regex extracted: %s from '%s'",
                    custom_time, stream_name[:50]
                )

    # Early exit for empty streams
    if not normalized.normalized:
        result = ClassifiedStream(
            category=StreamCategory.PLACEHOLDER,
            normalized=normalized,
        )
    else:
        text = normalized.normalized

        # Step 2: Check placeholder patterns
        if is_placeholder(text):
            result = ClassifiedStream(
                category=StreamCategory.PLACEHOLDER,
                normalized=normalized,
            )
        else:
            # Detect league and sport hints (useful for all categories)
            league_hint = detect_league_hint(text)
            sport_hint = detect_sport_hint(text)

            # Step 3: Check for event card
            if is_event_card(text, league_event_type):
                event_hint = extract_event_card_hint(text)
                result = ClassifiedStream(
                    category=StreamCategory.EVENT_CARD,
                    normalized=normalized,
                    event_hint=event_hint,
                    league_hint=league_hint,
                    sport_hint=sport_hint,
                )

            # Step 4: Try custom regex for team extraction (if configured)
            elif custom_regex and custom_regex.teams_enabled:
                team1, team2, success = extract_teams_with_custom_regex(text, custom_regex)
                if success:
                    result = ClassifiedStream(
                        category=StreamCategory.TEAM_VS_TEAM,
                        normalized=normalized,
                        team1=team1,
                        team2=team2,
                        separator_found="custom_regex",
                        league_hint=league_hint,
                        sport_hint=sport_hint,
                        custom_regex_used=True,
                    )

            # Step 5: Check for game separator (builtin fallback)
            if result is None:
                separator, sep_position = find_game_separator(text)
                if separator:
                    team1, team2 = extract_teams_from_separator(text, separator, sep_position)

                    # Only classify as TEAM_VS_TEAM if we got at least one team
                    if team1 or team2:
                        result = ClassifiedStream(
                            category=StreamCategory.TEAM_VS_TEAM,
                            normalized=normalized,
                            team1=team1,
                            team2=team2,
                            separator_found=separator,
                            league_hint=league_hint,
                            sport_hint=sport_hint,
                        )

            # Step 6: Default to placeholder if we can't classify
            if result is None:
                result = ClassifiedStream(
                    category=StreamCategory.PLACEHOLDER,
                    normalized=normalized,
                    league_hint=league_hint,
                    sport_hint=sport_hint,
                )

    logger.debug(
        "[CLASSIFY] '%s' -> %s (league=%s, sport=%s, teams=%s/%s)",
        stream_name[:50],
        result.category.value,
        result.league_hint,
        result.sport_hint,
        result.team1,
        result.team2,
    )

    return result


def classify_streams(
    stream_names: list[str],
    league_event_type: str | None = None,
    custom_regex: CustomRegexConfig | None = None,
) -> list[ClassifiedStream]:
    """Classify multiple streams.

    Args:
        stream_names: List of raw stream names
        league_event_type: Optional event_type from leagues table
        custom_regex: Optional custom regex configuration for team extraction

    Returns:
        List of ClassifiedStream objects
    """
    return [classify_stream(name, league_event_type, custom_regex) for name in stream_names]
