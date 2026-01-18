"""Exception keywords operations.

Read-only access to consolidation_exception_keywords for lifecycle service.
Full CRUD is in database/exception_keywords.py.
"""

import re
from sqlite3 import Connection

from teamarr.database.exception_keywords import ExceptionKeyword, get_all_keywords


def get_exception_keywords(conn: Connection, enabled_only: bool = True) -> list[ExceptionKeyword]:
    """Get all consolidation exception keywords.

    Args:
        conn: Database connection
        enabled_only: Only return enabled keywords

    Returns:
        List of ExceptionKeyword objects
    """
    return get_all_keywords(conn, include_disabled=not enabled_only)


def _make_keyword_pattern(keyword: str) -> str:
    """Create regex pattern with smart boundaries for keyword matching.

    Uses \\b for word characters, (?<!\\w)/(?!\\w) for non-word characters.
    This allows keywords like "(ESP)" to match correctly while still preventing
    false positives like "Eli" matching "Pelicans".

    Args:
        keyword: The keyword to create a pattern for

    Returns:
        Regex pattern string
    """
    escaped = re.escape(keyword.lower())

    # Start boundary: \b if keyword starts with word char, else (?<!\w)
    if keyword and re.match(r"\w", keyword[0]):
        start = r"\b"
    else:
        start = r"(?<!\w)"

    # End boundary: \b if keyword ends with word char, else (?!\w)
    if keyword and re.match(r"\w", keyword[-1]):
        end = r"\b"
    else:
        end = r"(?!\w)"

    return start + escaped + end


def check_exception_keyword(
    stream_name: str,
    keywords: list[ExceptionKeyword],
) -> tuple[str | None, str | None]:
    """Check if stream name matches any exception keyword.

    Uses smart boundary matching to avoid false positives like "Eli" matching
    "Pelicans", while still supporting keywords with special characters like "(ESP)".

    Args:
        stream_name: Stream name to check
        keywords: List of ExceptionKeyword objects

    Returns:
        Tuple of (matched_keyword, behavior) or (None, None) if no match
    """
    stream_lower = stream_name.lower()

    for kw in keywords:
        for variant in kw.keyword_list:
            pattern = _make_keyword_pattern(variant)
            if re.search(pattern, stream_lower):
                return (variant, kw.behavior)

    return (None, None)
