import { useState, useMemo } from "react"
import { useQueries } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Search, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { getLeagueTeams, type CachedTeam } from "@/api/teams"
import type { TeamFilterEntry } from "@/api/types"

interface TeamPickerProps {
  leagues: string[]
  selectedTeams: TeamFilterEntry[]
  onSelectionChange: (teams: TeamFilterEntry[]) => void
  placeholder?: string
}

interface LeagueTeams {
  league: string
  teams: CachedTeam[]
  isExpanded: boolean
}

export function TeamPicker({
  leagues,
  selectedTeams,
  onSelectionChange,
  placeholder = "Search teams...",
}: TeamPickerProps) {
  const [search, setSearch] = useState("")
  const [expandedLeagues, setExpandedLeagues] = useState<Set<string>>(new Set())

  // Fetch teams for all leagues
  const teamQueries = useQueries({
    queries: leagues.map((league) => ({
      queryKey: ["leagueTeams", league],
      queryFn: () => getLeagueTeams(league),
      staleTime: 5 * 60 * 1000, // 5 minutes
      enabled: leagues.length > 0,
    })),
  })

  const isLoading = teamQueries.some((q) => q.isLoading)

  // Combine all teams grouped by league
  const teamsByLeague = useMemo(() => {
    const result: LeagueTeams[] = []
    leagues.forEach((league, index) => {
      const query = teamQueries[index]
      if (query.data) {
        result.push({
          league,
          teams: query.data,
          isExpanded: expandedLeagues.has(league),
        })
      }
    })
    return result
  }, [leagues, teamQueries, expandedLeagues])

  // Filter teams by search
  const filteredByLeague = useMemo(() => {
    if (!search.trim()) return teamsByLeague
    const searchLower = search.toLowerCase()
    return teamsByLeague
      .map((lg) => ({
        ...lg,
        teams: lg.teams.filter(
          (t) =>
            t.team_name.toLowerCase().includes(searchLower) ||
            (t.team_abbrev && t.team_abbrev.toLowerCase().includes(searchLower)) ||
            (t.team_short_name && t.team_short_name.toLowerCase().includes(searchLower))
        ),
      }))
      .filter((lg) => lg.teams.length > 0)
  }, [teamsByLeague, search])

  // Toggle league expansion
  const toggleLeague = (league: string) => {
    setExpandedLeagues((prev) => {
      const next = new Set(prev)
      if (next.has(league)) {
        next.delete(league)
      } else {
        next.add(league)
      }
      return next
    })
  }

  // Check if team is selected
  const isTeamSelected = (team: CachedTeam) => {
    return selectedTeams.some(
      (t) => t.provider === team.provider && t.team_id === team.provider_team_id && t.league === team.league
    )
  }

  // Toggle team selection
  const toggleTeam = (team: CachedTeam) => {
    const isSelected = isTeamSelected(team)
    if (isSelected) {
      onSelectionChange(
        selectedTeams.filter(
          (t) => !(t.provider === team.provider && t.team_id === team.provider_team_id && t.league === team.league)
        )
      )
    } else {
      onSelectionChange([
        ...selectedTeams,
        {
          provider: team.provider,
          team_id: team.provider_team_id,
          league: team.league,
          name: team.team_name,
        },
      ])
    }
  }

  // Remove selected team
  const removeTeam = (team: TeamFilterEntry) => {
    onSelectionChange(
      selectedTeams.filter(
        (t) => !(t.provider === team.provider && t.team_id === team.team_id && t.league === team.league)
      )
    )
  }

  // Select all teams in a league
  const selectAllInLeague = (teams: CachedTeam[]) => {
    const newTeams = teams.filter((t) => !isTeamSelected(t)).map((t) => ({
      provider: t.provider,
      team_id: t.provider_team_id,
      league: t.league,
      name: t.team_name,
    }))
    onSelectionChange([...selectedTeams, ...newTeams])
  }

  // Clear all teams in a league
  const clearLeague = (league: string) => {
    onSelectionChange(selectedTeams.filter((t) => t.league !== league))
  }

  // Count selected in league
  const countSelectedInLeague = (league: string) => {
    return selectedTeams.filter((t) => t.league === league).length
  }

  if (leagues.length === 0) {
    return (
      <div className="text-sm text-muted-foreground p-4 border rounded-md">
        Select leagues first to enable team filtering.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Selected teams badges */}
      {selectedTeams.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedTeams.slice(0, 10).map((team) => (
            <Badge
              key={`${team.provider}-${team.team_id}`}
              variant="secondary"
              className="gap-1 pr-1"
            >
              {team.name}
              <button
                onClick={() => removeTeam(team)}
                className="ml-1 rounded-full hover:bg-muted-foreground/20"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {selectedTeams.length > 10 && (
            <Badge variant="outline">+{selectedTeams.length - 10} more</Badge>
          )}
        </div>
      )}

      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={placeholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-8"
        />
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="text-sm text-muted-foreground p-4 text-center">
          Loading teams...
        </div>
      )}

      {/* Team list by league */}
      <div className="border rounded-md max-h-80 overflow-y-auto">
        {filteredByLeague.map((lg) => (
          <div key={lg.league} className="border-b last:border-b-0">
            {/* League header */}
            <button
              onClick={() => toggleLeague(lg.league)}
              className="w-full flex items-center justify-between p-2 hover:bg-muted/50 text-sm font-medium"
            >
              <div className="flex items-center gap-2">
                {expandedLeagues.has(lg.league) ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
                <span className="uppercase">{lg.league}</span>
                <span className="text-muted-foreground font-normal">
                  ({countSelectedInLeague(lg.league)} selected)
                </span>
              </div>
              <div className="flex gap-2 text-xs" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => selectAllInLeague(lg.teams)}
                  className="text-primary hover:underline"
                >
                  Select All
                </button>
                <button
                  onClick={() => clearLeague(lg.league)}
                  className="text-muted-foreground hover:underline"
                >
                  Clear
                </button>
              </div>
            </button>

            {/* Teams list */}
            {expandedLeagues.has(lg.league) && (
              <div className="px-2 pb-2 space-y-1">
                {lg.teams.map((team) => (
                  <label
                    key={`${team.provider}-${team.provider_team_id}`}
                    className="flex items-center gap-2 p-1.5 rounded hover:bg-muted/50 cursor-pointer"
                  >
                    <Checkbox
                      checked={isTeamSelected(team)}
                      onCheckedChange={() => toggleTeam(team)}
                    />
                    {team.logo_url && (
                      <img
                        src={team.logo_url}
                        alt=""
                        className="h-5 w-5 object-contain"
                        onError={(e) => {
                          ;(e.target as HTMLImageElement).style.display = "none"
                        }}
                      />
                    )}
                    <span className="text-sm">{team.team_name}</span>
                    {team.team_abbrev && (
                      <span className="text-xs text-muted-foreground">
                        ({team.team_abbrev})
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* No results */}
        {filteredByLeague.length === 0 && !isLoading && (
          <div className="text-sm text-muted-foreground p-4 text-center">
            {search ? "No teams match your search." : "No teams available."}
          </div>
        )}
      </div>
    </div>
  )
}
