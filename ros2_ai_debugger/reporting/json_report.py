"""JSON report (machine-readable; includes the snapshot so it can be replayed)."""
from __future__ import annotations

import json

from ros2_ai_debugger.reporting.report import Report

REPORT_SCHEMA_VERSION = 1


def report_to_dict(report: Report) -> dict:
    ai = report.ai
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": {"name": "ros2-ai-debugger", "version": report.tool_version},
        "generated_at": report.generated_at,
        "overall": report.overall().label if report.overall() is not None else "ok",
        "redacted": report.redacted,
        "ai": {"mode": ai.mode, "provider": ai.provider, "detail": ai.detail, "summary": ai.summary,
               "missing_information": ai.missing_information, "validation_warnings": ai.warnings},
        "findings": [f.to_dict() for f in report.findings],
        "snapshot": report.snapshot.to_dict(),
    }


def render_json(report: Report) -> str:
    return json.dumps(report_to_dict(report), indent=2, sort_keys=False) + "\n"
