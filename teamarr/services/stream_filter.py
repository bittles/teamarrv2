"""Stream filtering service for event EPG groups.

Provides regex-based stream filtering and team name extraction.
Uses the 'regex' module if available for advanced patterns,
otherwise falls back to standard 're' module.
"""

import re
from dataclasses import dataclass, field
from re import Pattern

# Try to import 'regex' module which supports advanced features
try:
    import regex

    REGEX_MODULE = regex
    SUPPORTS_VARIABLE_LOOKBEHIND = True
except ImportError:
    REGEX_MODULE = re
    SUPPORTS_VARIABLE_LOOKBEHIND = False


@dataclass
class StreamFilterConfig:
    """Configuration for stream filtering."""

    include_regex: str | None = None
    include_enabled: bool = False
    exclude_regex: str | None = None
    exclude_enabled: bool = False
    custom_teams_regex: str | None = None
    custom_teams_enabled: bool = False
    skip_builtin: bool = False


@dataclass
class FilterResult:
    """Result of stream filtering."""

    # Streams that passed all filters
    passed: list[dict] = field(default_factory=list)

    # Filtering stats
    total_input: int = 0
    filtered_include: int = 0  # Didn't match include pattern
    filtered_exclude: int = 0  # Matched exclude pattern
    passed_count: int = 0


@dataclass
class TeamExtractionResult:
    """Result of team name extraction from a stream name."""

    success: bool = False
    team1: str | None = None
    team2: str | None = None
    method: str = ""  # 'custom', 'builtin', 'none'


def compile_pattern(pattern: str | None, ignore_case: bool = True) -> Pattern | None:
    """Compile a regex pattern with error handling.

    Args:
        pattern: The regex pattern string to compile
        ignore_case: Whether to use case-insensitive matching

    Returns:
        Compiled regex pattern or None on error/empty input
    """
    if not pattern or not pattern.strip():
        return None

    flags = REGEX_MODULE.IGNORECASE if ignore_case else 0

    try:
        return REGEX_MODULE.compile(pattern.strip(), flags)
    except Exception:
        return None


def validate_pattern(pattern: str | None) -> tuple[bool, str | None]:
    """Validate a regex pattern without compiling for reuse.

    Args:
        pattern: The regex pattern string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not pattern or not pattern.strip():
        return (True, None)

    try:
        REGEX_MODULE.compile(pattern.strip())
        return (True, None)
    except Exception as e:
        return (False, str(e))


class StreamFilter:
    """Filters streams based on regex patterns."""

    def __init__(self, config: StreamFilterConfig):
        """Initialize stream filter.

        Args:
            config: Filter configuration
        """
        self.config = config
        self._include_pattern: Pattern | None = None
        self._exclude_pattern: Pattern | None = None
        self._teams_pattern: Pattern | None = None

        # Compile patterns
        if config.include_enabled and config.include_regex:
            self._include_pattern = compile_pattern(config.include_regex)

        if config.exclude_enabled and config.exclude_regex:
            self._exclude_pattern = compile_pattern(config.exclude_regex)

        if config.custom_teams_enabled and config.custom_teams_regex:
            self._teams_pattern = compile_pattern(config.custom_teams_regex)

    def filter(self, streams: list[dict]) -> FilterResult:
        """Apply filters and return filtered streams with stats.

        Args:
            streams: List of stream dicts with at least 'id' and 'name' keys

        Returns:
            FilterResult with passed streams and stats
        """
        result = FilterResult(total_input=len(streams))

        for stream in streams:
            name = stream.get("name", "")

            # Include filter: stream must match
            if self._include_pattern:
                if not self._include_pattern.search(name):
                    result.filtered_include += 1
                    continue

            # Exclude filter: stream must NOT match
            if self._exclude_pattern:
                if self._exclude_pattern.search(name):
                    result.filtered_exclude += 1
                    continue

            # Stream passed all filters
            result.passed.append(stream)

        result.passed_count = len(result.passed)
        return result

    def extract_teams(self, stream_name: str) -> TeamExtractionResult:
        """Extract team names from a stream name.

        Uses custom regex if configured, otherwise falls back to
        builtin patterns (unless skip_builtin is set).

        Args:
            stream_name: The stream name to parse

        Returns:
            TeamExtractionResult with extracted team names
        """
        # Try custom pattern first
        if self._teams_pattern:
            match = self._teams_pattern.search(stream_name)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    return TeamExtractionResult(
                        success=True,
                        team1=groups[0],
                        team2=groups[1],
                        method="custom",
                    )
                # Try named groups
                try:
                    team1 = match.group("team1")
                    team2 = match.group("team2")
                    return TeamExtractionResult(
                        success=True, team1=team1, team2=team2, method="custom"
                    )
                except (IndexError, KeyError):
                    pass

        # Skip builtin if configured
        if self.config.skip_builtin:
            return TeamExtractionResult(success=False, method="none")

        # Builtin patterns for common formats
        return self._extract_teams_builtin(stream_name)

    def _extract_teams_builtin(self, stream_name: str) -> TeamExtractionResult:
        """Extract teams using builtin patterns.

        Supports common formats:
        - "Team A vs Team B"
        - "Team A @ Team B"
        - "Team A v Team B"
        - "Team A - Team B"
        """
        # Common separators: vs, v, @, at, -
        patterns = [
            r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s*[\|\-\[]|$)",
            r"(.+?)\s+@\s+(.+?)(?:\s*[\|\-\[]|$)",
            r"(.+?)\s+(?:at)\s+(.+?)(?:\s*[\|\-\[]|$)",
            r"(.+?)\s+v\s+(.+?)(?:\s*[\|\-\[]|$)",
            r"(.+?)\s+-\s+(.+?)(?:\s*[\|\-\[]|$)",
        ]

        for pattern in patterns:
            match = REGEX_MODULE.search(pattern, stream_name, REGEX_MODULE.IGNORECASE)
            if match:
                team1 = match.group(1).strip()
                team2 = match.group(2).strip()
                if team1 and team2:
                    return TeamExtractionResult(
                        success=True, team1=team1, team2=team2, method="builtin"
                    )

        return TeamExtractionResult(success=False, method="none")


def create_filter_from_group(group) -> StreamFilter:
    """Create a StreamFilter from an EventEPGGroup.

    Args:
        group: EventEPGGroup dataclass or dict with filter config

    Returns:
        Configured StreamFilter instance
    """
    if hasattr(group, "stream_include_regex"):
        # Dataclass
        config = StreamFilterConfig(
            include_regex=group.stream_include_regex,
            include_enabled=group.stream_include_regex_enabled,
            exclude_regex=group.stream_exclude_regex,
            exclude_enabled=group.stream_exclude_regex_enabled,
            custom_teams_regex=group.custom_regex_teams,
            custom_teams_enabled=group.custom_regex_teams_enabled,
            skip_builtin=group.skip_builtin_filter,
        )
    else:
        # Dict
        config = StreamFilterConfig(
            include_regex=group.get("stream_include_regex"),
            include_enabled=bool(group.get("stream_include_regex_enabled")),
            exclude_regex=group.get("stream_exclude_regex"),
            exclude_enabled=bool(group.get("stream_exclude_regex_enabled")),
            custom_teams_regex=group.get("custom_regex_teams"),
            custom_teams_enabled=bool(group.get("custom_regex_teams_enabled")),
            skip_builtin=bool(group.get("skip_builtin_filter")),
        )

    return StreamFilter(config)
