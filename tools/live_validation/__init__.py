"""Tracked bounded live-validation runner for released PNC assignments.

Modules:

- ``binding`` — released-assignment document, strict parse, static checks.
- ``cases`` — the frozen V44 case registry (selection derives everything).
- ``events`` — runner-owned attribution of actual input dispatch events.
- ``journal`` — fsynced logical-attempt journal.
- ``evidence`` — typed v3 result document, serializer, and totals.
- ``validate`` — fail-closed offline validator binding a result to its release.
- ``v2`` — read-only inspector for the historical live030 evidence format.
- ``annotation`` — bounded tester-annotation exchange for measured controls.
- ``runner`` — the orchestration core.
"""
