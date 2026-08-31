# Global Work Queue

`ppa.suggested.action` is PPA's single work-item record. It unifies actionable work from email, meetings, and future communication sources without creating a parallel task model.

```
Communication sources
        ↓
Messages / Meetings
        ↓
AI analysis
        ↓
Suggested Actions
        ↓
Global Work Queue
        ↓
Human confirmation and work lifecycle
```

Suggested Actions start as `to_confirm`. They are not Odoo Project tasks or activities. Only an explicit **Confirm** action may invoke the pre-existing downstream task/activity workflow. AI analysis, ingestion replay, and re-analysis never confirm an action automatically.

The lifecycle is `to_confirm`, `confirmed`, `in_progress`, `waiting`, `completed`, and `rejected`. Waiting records retain optional reason, since, and waiting-on text. Completed and rejected work is excluded from the default queue but remains available through Completed and search filters.

The Work menu provides Global Work Queue, My Work, To Confirm, Waiting, and Completed. The primary queue orders critical, important, normal, then low priority; within a priority it orders deadline then newest work. Operators can filter by ownership, Flow, Project, Company, source category, priority, state, and deadline.

Work context is derived conservatively from its source. Message actions inherit the Message Flow, Project, Company, and resolved owner. Meeting actions inherit the Meeting Flow, Project, and Company. A Flow's Project takes precedence to keep the context coherent. Manual owner, Flow, and Project changes stay on the work item and historical actions are never deleted or reset by re-analysis.

For a future Daily Brief, query the same model for active critical work, overdue work, work due today, waiting work, new `to_confirm` work, and important work missing an owner or Flow. No Daily Brief is implemented in this phase.
