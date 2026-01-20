import { useState, useMemo } from "react"
import { GripVertical, ChevronDown, ChevronRight } from "lucide-react"

/**
 * Generic item interface for hierarchical sorting.
 * Items must have a group key and optional child key.
 */
export interface HierarchicalItem {
  id: number | string
  group: string           // The parent group key (e.g., sport code)
  groupLabel?: string     // Display label for the group (e.g., sport display name)
  child?: string | null   // The child item (e.g., league_code), null = group-level item
  sortPriority: number    // Current sort order
  label: string           // Display label for this item
  metadata?: Record<string, unknown>  // Additional data for rendering
}

export interface GroupedItem {
  group: string
  groupLabel: string                   // Display label for this group
  groupItem: HierarchicalItem | null   // Group-level item (if exists)
  children: HierarchicalItem[]
}

export interface HierarchicalSortableProps {
  /** Items to display and sort */
  items: HierarchicalItem[]
  /** Callback when items are reordered. Returns new order as array of {group, child, priority} */
  onReorder: (newOrder: Array<{ group: string; child: string | null; priority: number }>) => Promise<void>
  /** Optional callback when an item is deleted */
  onDelete?: (item: HierarchicalItem) => Promise<void>
  /** Whether delete is in progress */
  isDeleting?: boolean
  /** Custom renderer for group header content (after chevron and label) */
  renderGroupExtra?: (group: GroupedItem) => React.ReactNode
  /** Custom renderer for child item content (after label) */
  renderChildExtra?: (item: HierarchicalItem) => React.ReactNode
  /** Whether to show delete buttons */
  showDelete?: boolean
  /** Placeholder when no items */
  emptyMessage?: string
  /** Whether groups are expanded by default (defaults to false - collapsed) */
  defaultExpanded?: boolean
}

export function HierarchicalSortable({
  items,
  onReorder,
  onDelete,
  isDeleting = false,
  renderGroupExtra,
  renderChildExtra,
  showDelete = true,
  emptyMessage = "No items configured.",
  defaultExpanded = false,
}: HierarchicalSortableProps) {
  const [draggedChild, setDraggedChild] = useState<HierarchicalItem | null>(null)
  const [draggedGroup, setDraggedGroup] = useState<string | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    if (defaultExpanded) {
      return new Set(items.map(i => i.group))
    }
    return new Set()
  })

  // Group items by their group key
  const groupedItems = useMemo(() => {
    const groups: GroupedItem[] = []
    const groupMap = new Map<string, GroupedItem>()

    // First pass: identify all groups and track group labels
    const groupLabels = new Map<string, string>()

    for (const item of items) {
      if (!groupMap.has(item.group)) {
        groupMap.set(item.group, {
          group: item.group,
          groupLabel: item.group, // Default to group key, will be updated
          groupItem: null,
          children: [],
        })
      }

      // Track the best groupLabel (prefer from group-level item, or first child with groupLabel)
      if (item.groupLabel && !groupLabels.has(item.group)) {
        groupLabels.set(item.group, item.groupLabel)
      }

      const group = groupMap.get(item.group)!
      if (item.child === null || item.child === undefined) {
        group.groupItem = item
        // Group-level item's groupLabel takes priority
        if (item.groupLabel) {
          groupLabels.set(item.group, item.groupLabel)
        }
      } else {
        group.children.push(item)
      }
    }

    // Apply groupLabels to groups
    for (const [groupKey, label] of groupLabels) {
      const group = groupMap.get(groupKey)
      if (group) {
        group.groupLabel = label
      }
    }

    // Sort groups by their group-level priority (or first child priority)
    const sortedGroups = Array.from(groupMap.entries()).sort((a, b) => {
      const aPri = a[1].groupItem?.sortPriority ?? a[1].children[0]?.sortPriority ?? 9999
      const bPri = b[1].groupItem?.sortPriority ?? b[1].children[0]?.sortPriority ?? 9999
      return aPri - bPri
    })

    for (const [, group] of sortedGroups) {
      // Sort children within each group
      group.children.sort((a, b) => a.sortPriority - b.sortPriority)
      groups.push(group)
    }

    return groups
  }, [items])

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) {
        next.delete(group)
      } else {
        next.add(group)
      }
      return next
    })
  }

  // Build reorder data from current grouped state
  const buildReorderData = (groups: GroupedItem[]) => {
    const result: Array<{ group: string; child: string | null; priority: number }> = []
    let priority = 0
    for (const group of groups) {
      if (group.groupItem) {
        result.push({ group: group.group, child: null, priority: priority++ })
      }
      for (const child of group.children) {
        result.push({ group: group.group, child: child.child ?? null, priority: priority++ })
      }
    }
    return result
  }

  // Group-level drag handlers
  const handleGroupDragStart = (e: React.DragEvent, group: string) => {
    setDraggedGroup(group)
    setDraggedChild(null)
    e.dataTransfer.effectAllowed = "move"
  }

  const handleGroupDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
  }

  const handleGroupDrop = async (e: React.DragEvent, targetGroup: string) => {
    e.preventDefault()
    if (!draggedGroup || draggedGroup === targetGroup) {
      setDraggedGroup(null)
      return
    }

    // Reorder groups
    const newGroups = [...groupedItems]
    const draggedIndex = newGroups.findIndex(g => g.group === draggedGroup)
    const targetIndex = newGroups.findIndex(g => g.group === targetGroup)

    if (draggedIndex === -1 || targetIndex === -1) {
      setDraggedGroup(null)
      return
    }

    const [dragged] = newGroups.splice(draggedIndex, 1)
    newGroups.splice(targetIndex, 0, dragged)

    setDraggedGroup(null)

    // Trigger reorder callback
    await onReorder(buildReorderData(newGroups))
  }

  // Child-level drag handlers
  const handleChildDragStart = (e: React.DragEvent, item: HierarchicalItem) => {
    setDraggedChild(item)
    setDraggedGroup(null)
    e.dataTransfer.effectAllowed = "move"
    e.stopPropagation()
  }

  const handleChildDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
  }

  const handleChildDrop = async (e: React.DragEvent, targetItem: HierarchicalItem) => {
    e.preventDefault()
    e.stopPropagation()

    if (!draggedChild || draggedChild.id === targetItem.id) {
      setDraggedChild(null)
      return
    }

    // Only allow reordering within the same group
    if (draggedChild.group !== targetItem.group) {
      setDraggedChild(null)
      return
    }

    // Find the group
    const groupIndex = groupedItems.findIndex(g => g.group === draggedChild.group)
    if (groupIndex === -1) {
      setDraggedChild(null)
      return
    }

    const group = groupedItems[groupIndex]
    const draggedIndex = group.children.findIndex(c => c.id === draggedChild.id)
    const targetIndex = group.children.findIndex(c => c.id === targetItem.id)

    if (draggedIndex === -1 || targetIndex === -1) {
      setDraggedChild(null)
      return
    }

    // Create new groups array with reordered children
    const newGroups = groupedItems.map((g, i) => {
      if (i !== groupIndex) return g
      const newChildren = [...g.children]
      const [dragged] = newChildren.splice(draggedIndex, 1)
      newChildren.splice(targetIndex, 0, dragged)
      return { ...g, children: newChildren }
    })

    setDraggedChild(null)

    // Trigger reorder callback
    await onReorder(buildReorderData(newGroups))
  }

  const handleDelete = async (item: HierarchicalItem) => {
    if (onDelete) {
      await onDelete(item)
    }
  }

  if (groupedItems.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground">
        <p>{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {groupedItems.map((group, groupIndex) => (
        <div key={group.group} className="border rounded-md">
          {/* Group header - draggable */}
          <div
            className={`
              flex items-center gap-2 px-3 py-2 bg-muted/30
              ${draggedGroup === group.group ? "opacity-50 border-dashed" : "hover:bg-muted/50"}
              cursor-grab active:cursor-grabbing
            `}
            draggable
            onDragStart={(e) => handleGroupDragStart(e, group.group)}
            onDragOver={handleGroupDragOver}
            onDrop={(e) => handleGroupDrop(e, group.group)}
          >
            <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className="text-sm font-mono text-muted-foreground w-6">
              {groupIndex + 1}.
            </span>
            <button
              type="button"
              className="flex items-center gap-1 flex-1 text-left"
              onClick={() => toggleGroup(group.group)}
            >
              {expandedGroups.has(group.group) ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="font-medium">{group.groupLabel}</span>
            </button>
            {renderGroupExtra && renderGroupExtra(group)}
          </div>

          {/* Children - collapsible */}
          {expandedGroups.has(group.group) && group.children.length > 0 && (
            <div className="border-t pl-8 py-1 space-y-1">
              {group.children.map((child, childIndex) => (
                <div
                  key={child.id}
                  className={`
                    flex items-center gap-2 px-3 py-1.5 rounded-md
                    ${draggedChild?.id === child.id ? "opacity-50 border border-dashed" : "hover:bg-muted/30"}
                    cursor-grab active:cursor-grabbing
                  `}
                  draggable
                  onDragStart={(e) => handleChildDragStart(e, child)}
                  onDragOver={handleChildDragOver}
                  onDrop={(e) => handleChildDrop(e, child)}
                >
                  <GripVertical className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="text-xs font-mono text-muted-foreground w-6">
                    {childIndex + 1}.
                  </span>
                  <span className="flex-1 text-sm">
                    {child.label}
                  </span>
                  {renderChildExtra && renderChildExtra(child)}
                  {showDelete && onDelete && (
                    <button
                      type="button"
                      className="h-5 w-5 p-0 flex items-center justify-center rounded hover:bg-muted"
                      onClick={() => handleDelete(child)}
                      disabled={isDeleting}
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <path d="M3 6h18" />
                        <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                        <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                      </svg>
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
