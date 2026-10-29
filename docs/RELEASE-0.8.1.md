# 0.8.1: fresh quota across existing projects

Some 0.7 project stores still contained old signals.json snapshots. 0.8.0 selected these files merely because they existed, hiding the fresh account collector and reporting quota as unknown. This update uses the existing collector when the project has no usable current quota observation, without changing any checkpoint, task policy, ownership or native permission.

Current project observations, all collector windows and local non-quota limits are retained. A pinned account identity must match; an explicit collector selection remains authoritative even if stale. If neither source is usable, quota remains unknown. Persistent pauses, grants and mandatory recovery reviews remain retired.

Eight new regression cases reproduce four failures on 0.8.0 and pass on the repair; the complete focused suite has 61 tests. Native read-only checks and protected-state comparisons are recorded privately per affected chat. No project implementation or native trial is restarted.
