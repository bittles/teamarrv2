"""Fuzzy string matching for team names.

Uses rapidfuzz for fast, maintenance-free fuzzy matching.
Provides pattern generation and matching utilities for the codebase.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from unidecode import unidecode

from teamarr.core import Team

# Common abbreviations to expand for better matching
# Key: abbreviation (lowercase), Value: expansion
ABBREVIATIONS = {
    # UFC/MMA
    "fn": "fight night",
    "ufc fn": "ufc fight night",
    "ppv": "pay per view",
    # Sports generic
    "vs": "versus",
    "v": "versus",
}


# NOTE: MASCOT_WORDS was removed in favor of deriving distinctiveness from provider data.
# Pattern distinctiveness is now determined by comparing team.name vs team.short_name:
# - If short_name appears at the END of name → short_name is mascot (distinctive)
# - If short_name appears at the START of name → suffix is mascot (distinctive)
# This eliminates manual maintenance and works for any team from any provider.


@dataclass
class TeamPattern:
    """A searchable pattern for team matching.

    Attributes:
        pattern: The normalized pattern text (lowercase, no punctuation)
        is_distinctive: True if this pattern is unique enough to match on its own
                        (e.g., mascots like "Celtics", "Blackhawks")
                        False if it's a non-distinctive location that could match
                        multiple teams (e.g., "Boston", "Chicago")
        source: Debug info about where this pattern came from
    """

    pattern: str
    is_distinctive: bool
    source: str = ""


@dataclass
class FuzzyMatchResult:
    """Result of a fuzzy match."""

    matched: bool
    score: float
    pattern_used: str | None = None


class FuzzyMatcher:
    """Fuzzy string matcher for team/event names.

    Uses rapidfuzz for fast matching with configurable thresholds.
    """

    def __init__(
        self,
        threshold: float = 85.0,
        partial_threshold: float = 90.0,
    ):
        """Initialize matcher.

        Args:
            threshold: Minimum score for full string match (0-100)
            partial_threshold: Minimum score for partial/token match (0-100)
        """
        self.threshold = threshold
        self.partial_threshold = partial_threshold

    def generate_team_patterns(self, team: Team) -> list[TeamPattern]:
        """Generate all searchable patterns for a team.

        Returns patterns in priority order (most specific first).
        Patterns are normalized to match how stream text is normalized.

        Pattern distinctiveness is derived from provider data:
        - Full name: always distinctive (e.g., "Boston Celtics")
        - If name ends with short_name: short_name is mascot (distinctive),
          prefix is city (non-distinctive)
        - If name starts with short_name: short_name is location,
          suffix is mascot (distinctive)
        - Abbreviation: always distinctive (e.g., "BOS")
        """
        patterns: list[TeamPattern] = []
        seen: set[str] = set()

        def normalize(value: str) -> str:
            """Normalize pattern text for matching."""
            # Normalize: strip accents (é→e, ü→u), lowercase
            normalized = unidecode(value).lower().strip()
            # Remove punctuation (hyphens become spaces) - matches normalize_for_matching
            normalized = re.sub(r"[^\w\s]", " ", normalized)
            # Clean up whitespace
            normalized = " ".join(normalized.split())
            return normalized

        def add(value: str | None, is_distinctive: bool, source: str) -> None:
            if value:
                normalized = normalize(value)
                if normalized and normalized not in seen and len(normalized) >= 2:
                    seen.add(normalized)
                    patterns.append(TeamPattern(normalized, is_distinctive, source))

        # 1. Full name is always distinctive: "Boston Celtics"
        if team.name:
            add(team.name, is_distinctive=True, source="full_name")

        # 2. Derive city/mascot from name vs short_name comparison
        # This eliminates the need for manually maintained MASCOT_WORDS
        if team.name and team.short_name:
            name_norm = normalize(team.name)
            short_norm = normalize(team.short_name)

            if name_norm.endswith(" " + short_norm):
                # short_name is at END of name → it's the mascot
                # "Boston Celtics" with short_name="Celtics"
                # → "Celtics" is distinctive (mascot)
                # → "Boston" is non-distinctive (city)
                city = team.name[: -(len(team.short_name) + 1)].strip()
                add(city, is_distinctive=False, source="derived_city")
                add(team.short_name, is_distinctive=True, source="short_name_mascot")

            elif name_norm.startswith(short_norm + " "):
                # short_name is at START of name → it's the location/school
                # "Florida Atlantic Owls" with short_name="Florida Atlantic"
                # → "Florida Atlantic" is non-distinctive (school name alone is ambiguous)
                # → "Owls" is distinctive (mascot)
                mascot = team.name[len(team.short_name) + 1 :].strip()
                add(team.short_name, is_distinctive=False, source="short_name_location")
                add(mascot, is_distinctive=True, source="derived_mascot")

            else:
                # short_name doesn't match a simple prefix/suffix pattern
                # Treat it as distinctive (it's probably a unique identifier)
                add(team.short_name, is_distinctive=True, source="short_name")

        elif team.short_name:
            # No full name to compare against, treat short_name as distinctive
            add(team.short_name, is_distinctive=True, source="short_name")

        # 3. Abbreviation is always distinctive: "BOS", "CHI"
        add(team.abbreviation, is_distinctive=True, source="abbreviation")

        return patterns

    def _expand_abbreviations(self, text: str) -> str:
        """Expand known abbreviations in text for better matching.

        E.g., "UFC FN Prelims" -> "UFC Fight Night Prelims"
        """
        import re

        result = text.lower()

        # Sort by length descending to match longer abbreviations first
        # (e.g., "ufc fn" before "fn")
        for abbrev in sorted(ABBREVIATIONS.keys(), key=len, reverse=True):
            expansion = ABBREVIATIONS[abbrev]
            # Use word boundaries to avoid partial matches
            pattern = r"\b" + re.escape(abbrev) + r"\b"
            result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)

        return result

    # Minimum pattern length for substring matching
    # Prevents "chi" matching "chicago" when looking for Chicago Blackhawks
    # Patterns shorter than this use word boundary matching instead
    MIN_SUBSTRING_LENGTH = 5

    # Minimum coverage for non-distinctive substring matches
    # "boston" (6 chars) in "boston bruins" (13 chars) = 46% coverage → reject
    # "celtics" (7 chars) in "boston celtics" (14 chars) = 50% → but celtics is distinctive
    # This prevents city names from matching team names in different leagues
    MIN_COVERAGE_RATIO = 0.70

    def matches_any(
        self,
        patterns: list[TeamPattern],
        text: str,
    ) -> FuzzyMatchResult:
        """Check if any pattern matches within text.

        Uses different strategies based on pattern distinctiveness:

        For DISTINCTIVE patterns (mascots, full names, abbreviations):
        - Substring match (fast path)
        - Word boundary match for short patterns
        - Token set ratio / partial ratio for fuzzy matching

        For NON-DISTINCTIVE patterns (cities, locations):
        - Require 70%+ coverage for substring matches (prevents "boston" matching "boston bruins")
        - Word boundary match as fallback

        Args:
            patterns: List of TeamPattern with distinctiveness info
            text: Text to search within

        Returns:
            FuzzyMatchResult with match status and score
        """
        # Expand abbreviations before matching
        text_lower = self._expand_abbreviations(text)

        # Strategy 1: Full-name substring match (fastest path for exact matches)
        # Only for patterns that are likely full team names (contain a space)
        # "boston celtics" in text is a definitive match
        for tp in patterns:
            if tp.is_distinctive and " " in tp.pattern and tp.pattern in text_lower:
                return FuzzyMatchResult(matched=True, score=100.0, pattern_used=tp.pattern)

        # Strategy 2: Word boundary match for all DISTINCTIVE patterns
        # Mascots like "hawks" shouldn't match inside "blackhawks"
        # Single-word patterns MUST have word boundaries to avoid substring issues
        for tp in patterns:
            if tp.is_distinctive:
                word_pattern = r"\b" + re.escape(tp.pattern) + r"\b"
                if re.search(word_pattern, text_lower):
                    return FuzzyMatchResult(matched=True, score=100.0, pattern_used=tp.pattern)

        # Strategy 3: Substring match for NON-DISTINCTIVE patterns with coverage check
        # "boston" should only match if it covers most of the text (like a standalone search)
        # This prevents "boston" in "boston bruins" (46% coverage) from matching
        for tp in patterns:
            if not tp.is_distinctive and len(tp.pattern) >= self.MIN_SUBSTRING_LENGTH:
                if tp.pattern in text_lower:
                    # Check coverage: pattern length / text length
                    coverage = len(tp.pattern) / len(text_lower)
                    if coverage >= self.MIN_COVERAGE_RATIO:
                        return FuzzyMatchResult(matched=True, score=100.0, pattern_used=tp.pattern)
                # Fallback: word boundary match for multi-word non-distinctive patterns
                # e.g., "Florida Atlantic" in "Florida Atlantic vs UCF" should match
                if " " in tp.pattern:
                    word_pattern = r"\b" + re.escape(tp.pattern) + r"\b"
                    if re.search(word_pattern, text_lower):
                        return FuzzyMatchResult(matched=True, score=100.0, pattern_used=tp.pattern)

        # Strategy 4: Token set ratio for MULTI-WORD distinctive patterns
        # Good for "Atlanta Falcons" matching "Falcons @ Atlanta"
        # Only for multi-word patterns to avoid "hawks" matching "blackhawks"
        for tp in patterns:
            if tp.is_distinctive and " " in tp.pattern:
                score = fuzz.token_set_ratio(tp.pattern, text_lower)
                if score >= self.partial_threshold:
                    return FuzzyMatchResult(matched=True, score=score, pattern_used=tp.pattern)

        # Strategy 5: Partial ratio for MULTI-WORD distinctive patterns only
        # Only for patterns with spaces - single words would match as substrings
        # (e.g., "hawks" would match inside "blackhawks" with 100% partial_ratio)
        for tp in patterns:
            if tp.is_distinctive and " " in tp.pattern:
                score = fuzz.partial_ratio(tp.pattern, text_lower)
                if score >= self.partial_threshold:
                    return FuzzyMatchResult(matched=True, score=score, pattern_used=tp.pattern)

        return FuzzyMatchResult(matched=False, score=0.0)

    def best_match(
        self,
        pattern: str,
        candidates: list[str],
    ) -> tuple[str | None, float]:
        """Find the best matching candidate for a pattern.

        Args:
            pattern: Pattern to match
            candidates: List of candidate strings

        Returns:
            Tuple of (best_match, score) or (None, 0) if no match
        """
        best_candidate = None
        best_score = 0.0

        pattern_lower = pattern.lower()

        for candidate in candidates:
            candidate_lower = candidate.lower()

            # Try different scoring methods, take the best
            scores = [
                fuzz.ratio(pattern_lower, candidate_lower),
                fuzz.token_set_ratio(pattern_lower, candidate_lower),
                fuzz.partial_ratio(pattern_lower, candidate_lower),
            ]
            score = max(scores)

            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_score >= self.threshold:
            return best_candidate, best_score

        return None, 0.0


# Default singleton for convenience
_default_matcher: FuzzyMatcher | None = None


def get_matcher() -> FuzzyMatcher:
    """Get the default FuzzyMatcher instance."""
    global _default_matcher
    if _default_matcher is None:
        _default_matcher = FuzzyMatcher()
    return _default_matcher
