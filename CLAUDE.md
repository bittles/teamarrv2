# Teamarr v2 - Project Constitution

## Vision

Teamarr v2 is a complete rewrite of the data layer with a provider-agnostic architecture. The system fetches sports data from multiple sources (ESPN, TheSportsDB, future providers), normalizes it into a unified format, and presents it to consumers (EPG generation, channel management, UI) in a source-agnostic way.

**Users don't know or care where data comes from. They see teams, events, and EPG.**

---

## Core Principles

### 1. Single Source of Truth
- Each piece of logic exists in ONE place
- No copy-pasted ESPN field extraction across modules
- Provider quirks handled in provider, nowhere else

### 2. Type-Driven Design
- All data structures defined as **dataclasses**
- Consumers know exactly what fields exist
- No more `get('abbrev') or get('abbreviation')` fallback chains
- Attribute access: `event.home_team.name` not `event['home_team']['name']`

### 3. Clean Boundaries
```
Providers → Service → Consumers
   │           │          │
   │           │          └── orchestrator, matcher, routes
   │           └── caching, routing, fallbacks
   └── ESPN, TheSportsDB, etc. (raw API + normalization)
```

### 4. Testability
- Mock providers for unit tests
- Captured API responses for integration tests
- No logic that can only be tested against live APIs

### 5. No Premature Optimization
- Get it working correctly first
- Optimize only when measured as slow
- Simple code > clever code

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FLASK ROUTES                             │
│              (UI endpoints, API endpoints)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CONSUMERS                                │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ Orchestrator │  │ EventMatcher │  │ ChannelLifecycle   │    │
│  │              │  │              │  │                    │    │
│  │ Team-based   │  │ Stream→Event │  │ Create/update/     │    │
│  │ EPG generation│  │ matching     │  │ delete channels    │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│                                                                  │
│  All consumers work with normalized types: Event, Team, etc.    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SPORTS DATA SERVICE                           │
│                                                                  │
│  The abstraction layer. Single entry point for all sports data. │
│                                                                  │
│  Responsibilities:                                               │
│  - Provider selection (ESPN primary, others fallback/fill gaps) │
│  - Caching (provider-agnostic TTL cache)                        │
│  - Fallbacks (if provider A fails, try provider B)              │
│  - Merging (combine data from multiple sources if needed)       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│     ESPN PROVIDER       │     │   THESPORTSDB PROVIDER  │
│       (PRIMARY)         │     │       (FALLBACK)        │
│                         │     │                         │
│  ┌───────────────────┐  │     │  ┌───────────────────┐  │
│  │  ESPN Client      │  │     │  │  TSDB Client      │  │
│  │  (raw HTTP calls) │  │     │  │  (raw HTTP calls) │  │
│  └───────────────────┘  │     │  └───────────────────┘  │
│           │             │     │           │             │
│           ▼             │     │           ▼             │
│  ┌───────────────────┐  │     │  ┌───────────────────┐  │
│  │  ESPN Normalizer  │  │     │  │  TSDB Normalizer  │  │
│  │                   │  │     │  │                   │  │
│  │  Raw ESPN dict →  │  │     │  │  Raw TSDB dict →  │  │
│  │  Event, Team, etc │  │     │  │  Event, Team, etc │  │
│  └───────────────────┘  │     │  └───────────────────┘  │
│                         │     │                         │
│  Handles ALL ESPN       │     │  Handles ALL TSDB       │
│  quirks internally      │     │  quirks internally      │
└─────────────────────────┘     └─────────────────────────┘
```

---

## Decisions Log

### ✅ DECIDED

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Type System | **Dataclasses** | Clean attribute access, IDE support, can add methods, proper Python objects |
| 2 | ID Strategy | **Separate fields** (`id` + `provider`) | No string parsing, explicit, clean |
| 3 | Directory Structure | **Nested package** (`teamarr/`) | Proper Python package, clean imports |
| 5 | Provider Priority | **ESPN primary, others fallback** | ESPN is free/unlimited, others fill gaps where ESPN lacks coverage |
| 6 | Build Order | **Vertical slices** | End-to-end flows working early, validates architecture fast |

### ⏳ PENDING DECISION

| # | Topic | Status | Notes |
|---|-------|--------|-------|
| 4 | Provider Interface Methods | **Needs review** | See detailed analysis below |

---

## Provider Interface Methods - Under Review

### Current Proposal

Based on analysis of v1 usage patterns:

```python
class SportsProvider(ABC):
    """Abstract base class for sports data providers"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier: 'espn', 'thesportsdb'"""

    # === CORE - Used constantly ===

    @abstractmethod
    def get_team(self, team_id: str, league: str) -> Optional[Team]:
        """Fetch team information (logo, colors, basic info)"""

    @abstractmethod
    def get_team_schedule(self, team_id: str, league: str, days_ahead: int = 14) -> List[Event]:
        """Fetch upcoming events for a team"""

    @abstractmethod
    def get_events(self, league: str, date: date) -> List[Event]:
        """Fetch all events for a league on a date (scoreboard/live)"""

    @abstractmethod
    def get_event(self, event_id: str, league: str) -> Optional[Event]:
        """Fetch a specific event by ID (fallback for finished games)"""

    # === STATS ===

    @abstractmethod
    def get_team_stats(self, team_id: str, league: str) -> Optional[TeamStats]:
        """Fetch team statistics/standings (record, streak, rank)"""

    # === DISCOVERY - Team import, caches ===

    @abstractmethod
    def get_league_teams(self, league: str) -> List[Team]:
        """Get all teams in a league"""

    @abstractmethod
    def get_teams_by_conference(self, league: str) -> Dict[str, List[Team]]:
        """Get teams organized by conference (college sports)"""

    @abstractmethod
    def search_teams(self, query: str, league: Optional[str] = None) -> List[Team]:
        """Search for teams by name"""

    # === CAPABILITY ===

    @abstractmethod
    def supports_league(self, league: str) -> bool:
        """Check if this provider supports a league"""
```

### v1 Method Mapping

| v1 Method | v1 Location | Proposed v2 Method |
|-----------|-------------|-------------------|
| `get_team_schedule()` | orchestrator, event_matcher | `get_team_schedule()` |
| `get_scoreboard()` | orchestrator, event_matcher, league_detector | `get_events()` |
| `get_team_info()` | orchestrator, event_enricher | `get_team()` |
| `get_team_stats()` | orchestrator, template_engine | `get_team_stats()` |
| `get_event_summary()` | event_matcher (fallback) | `get_event()` |
| `get_league_teams()` | team import, league cache | `get_league_teams()` |
| `get_all_teams_by_conference()` | college team import | `get_teams_by_conference()` |
| `search_teams()` | team import UI | `search_teams()` |

### Open Questions

1. **Is this the right granularity?** Should any methods be combined or split?
2. **Are we missing anything?** Any v1 functionality not covered?
3. **Date handling for `get_events()`** - Single date OK, or need date range?
4. **Conference method** - Only needed for college, should it be optional/separate?

---

## Directory Structure

```
teamarrv2/
├── CLAUDE.md                 # This file - project constitution
├── README.md                 # User-facing documentation
├── requirements.txt
├── app.py                    # Flask application entry point
│
├── teamarr/
│   ├── __init__.py
│   │
│   ├── core/                 # Foundation - built first
│   │   ├── __init__.py
│   │   ├── types.py          # Dataclass definitions: Event, Team, Venue, etc.
│   │   └── interfaces.py     # SportsProvider ABC
│   │
│   ├── providers/            # Data sources
│   │   ├── __init__.py
│   │   ├── espn/
│   │   │   ├── __init__.py
│   │   │   ├── client.py     # Raw ESPN API calls
│   │   │   ├── normalizer.py # ESPN response → dataclasses
│   │   │   └── provider.py   # Implements SportsProvider
│   │   └── thesportsdb/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       ├── normalizer.py
│   │       └── provider.py
│   │
│   ├── services/             # Business logic layer
│   │   ├── __init__.py
│   │   ├── sports_data.py    # Main SportsDataService implementation
│   │   └── cache.py          # Provider-agnostic caching
│   │
│   ├── epg/                  # EPG generation
│   │   ├── __init__.py
│   │   ├── orchestrator.py   # Main EPG generation coordinator
│   │   ├── generator.py      # XMLTV output generation
│   │   ├── template_engine.py# Variable substitution
│   │   ├── filler.py         # Pre/post game filler generation
│   │   ├── event_matcher.py  # Stream name → Event matching
│   │   ├── team_matcher.py   # Team name normalization/matching
│   │   └── league_detector.py# Multi-sport league detection
│   │
│   ├── channels/             # Channel lifecycle management
│   │   ├── __init__.py
│   │   ├── lifecycle.py      # Create/update/delete channels
│   │   └── reconciliation.py # Orphan detection, drift correction
│   │
│   ├── integrations/         # External service clients
│   │   ├── __init__.py
│   │   └── dispatcharr.py    # Dispatcharr API client
│   │
│   ├── database/             # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py     # Connection management
│   │   ├── migrations.py     # Schema migrations
│   │   └── schema.sql        # Base schema
│   │
│   └── utils/                # Shared utilities
│       ├── __init__.py
│       ├── time.py           # Timezone handling
│       └── logging.py        # Logging configuration
│
├── templates/                # Jinja2 templates (port from v1)
├── static/                   # Static assets (port from v1)
│
└── tests/
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures
    ├── fixtures/             # Sample API responses
    │   ├── espn/
    │   └── thesportsdb/
    ├── unit/
    │   ├── test_types.py
    │   ├── test_espn_normalizer.py
    │   └── test_sports_service.py
    └── integration/
        └── test_epg_generation.py
```

---

## Core Types (Dataclasses)

```python
# teamarr/core/types.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

@dataclass
class Team:
    id: str                    # Raw provider ID ("133604")
    provider: str              # "espn" | "thesportsdb"
    name: str                  # Display name ("Detroit Pistons")
    short_name: str            # Short name ("Pistons")
    abbreviation: str          # Abbreviation ("DET")
    league: str                # League identifier
    logo_url: Optional[str] = None
    color: Optional[str] = None  # Hex color without #

@dataclass
class Venue:
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

@dataclass
class EventStatus:
    state: str                 # "scheduled" | "live" | "final" | "postponed" | "cancelled"
    detail: Optional[str] = None      # "1st Quarter", "Final", "Postponed - Weather"
    period: Optional[int] = None      # Current period/quarter/half
    clock: Optional[str] = None       # Game clock if live

@dataclass
class Event:
    id: str                    # Raw provider ID
    provider: str              # "espn" | "thesportsdb"
    name: str                  # "Detroit Pistons at Indiana Pacers"
    short_name: str            # "DET @ IND"
    start_time: datetime       # UTC datetime
    home_team: Team
    away_team: Team
    status: EventStatus
    league: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[Venue] = None
    broadcasts: List[str] = None  # ["ESPN", "ABC"]
    season_year: Optional[int] = None
    season_type: Optional[str] = None  # "regular" | "postseason"

    def __post_init__(self):
        if self.broadcasts is None:
            self.broadcasts = []

@dataclass
class TeamStats:
    record: str                # "10-5" or "6-2-4" (W-D-L)
    home_record: Optional[str] = None
    away_record: Optional[str] = None
    streak: Optional[str] = None      # "W3", "L2"
    rank: Optional[int] = None        # For college sports
    conference: Optional[str] = None
    division: Optional[str] = None
```

---

## Provider Selection Strategy

**ESPN is always primary.** TheSportsDB and others are fallbacks or fill coverage gaps.

```python
class SportsDataService:
    def __init__(self):
        self.providers = [
            (ESPNProvider(), 1),           # Priority 1 (highest)
            (TheSportsDBProvider(), 2),    # Priority 2 (fallback)
        ]

    def get_events(self, league: str, date: date) -> List[Event]:
        # Try providers in priority order
        for provider, _ in sorted(self.providers, key=lambda p: p[1]):
            if provider.supports_league(league):
                try:
                    result = provider.get_events(league, date)
                    if result:
                        return result
                except Exception as e:
                    log.warning(f"{provider.name} failed: {e}")
                    continue
        return []
```

**Behavior:**
- NFL request → ESPN supports → ESPN handles
- AHL request → ESPN doesn't support → TheSportsDB handles
- ESPN API fails → Falls through to TheSportsDB (if it supports that league)

---

## Build Strategy: Vertical Slices

Build end-to-end functionality in slices, not horizontal layers:

### Slice 1: "Detroit Lions team-based EPG works"
- Team, Event, Venue dataclasses (minimal fields)
- ESPNProvider.get_team_schedule() for NFL only
- SportsDataService basic routing
- Orchestrator generates XMLTV for one team
- **Verify:** XML output matches v1

### Slice 2: "Event-based EPG works for NFL"
- Add EventStatus, more Event fields
- ESPNProvider.get_events() (scoreboard)
- EventMatcher basic matching
- **Verify:** Matched events generate correct EPG

### Slice 3: "Multiple leagues work"
- Add college basketball, soccer
- Test provider routing
- **Verify:** Different leagues work

### Slice 4: "Full feature parity"
- League detection tiers
- Channel lifecycle
- All template variables
- **Verify:** Matches v1 output exactly

### Slice 5: "TheSportsDB provider"
- New provider for gap leagues
- Test fallback behavior
- **Verify:** AHL/OHL work via TSDB

---

## What We're Keeping from v1

| Component | Status | Notes |
|-----------|--------|-------|
| Database schema | Keep | Well-designed, no changes needed |
| Database functions | Keep | No provider coupling |
| Flask route structure | Keep | URLs stay the same |
| Jinja templates | Keep | UI unchanged |
| Template variables | Keep | Same variable names |
| Dispatcharr client | Keep | Clean, no provider coupling |
| Team matcher logic | Port | Normalization tiers are good |
| League detector tiers | Port | Tier 1-4 logic is sound |
| Soccer multi-league | Port | Cache concept is good |

## What We're Discarding from v1

| Pattern | Reason |
|---------|--------|
| Scattered ESPN field extraction | Consolidated into normalizer |
| Multiple scoreboard caches | Single cache layer |
| `get('field') or get('other')` chains | Dataclasses with defined fields |
| Event enricher as separate module | Merged into provider |
| Inline ESPN quirk handling | Provider responsibility |
| 6000-line app.py | Split into proper modules |

---

## Success Criteria

v2 is ready when:

1. **Feature parity** - Everything v1 does, v2 does
2. **All tests pass** - Unit and integration
3. **ESPN works identically** - Same EPG output for same inputs
4. **TheSportsDB works** - At least one league functional
5. **No v1 code patterns** - No scattered field extraction, no fallback chains
6. **Documentation complete** - README, API docs, CLAUDE.md updated

---

## Reference

v1 codebase available at `../teamarr/` for reference during porting.

Key v1 files to reference:
- `api/espn_client.py` - ESPN API endpoints and caching
- `epg/orchestrator.py` - Team EPG generation logic
- `epg/event_matcher.py` - Event matching logic
- `epg/league_detector.py` - Tier 1-4 detection
- `epg/template_engine.py` - Variable substitution
- `epg/channel_lifecycle.py` - Channel CRUD
- `database/__init__.py` - All database functions
