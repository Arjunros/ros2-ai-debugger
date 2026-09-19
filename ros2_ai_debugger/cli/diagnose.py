"""`ros2 ai diagnose`."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from ros2_ai_debugger.analyzers import ExpectedConfig, analyze
from ros2_ai_debugger.analyzers.ai_prompt import (
    SYSTEM_PROMPT,
    build_payload,
    build_user_prompt,
    summarize_payload,
)
from ros2_ai_debugger.analyzers.ai_validation import AIResponseError
from ros2_ai_debugger.collectors import collect_snapshot, default_collectors
from ros2_ai_debugger.models import Severity, SystemSnapshot
from ros2_ai_debugger.privacy import Redactor
from ros2_ai_debugger.providers import (
    PROVIDERS,
    AIProvider,
    ProviderError,
    get_provider,
)
from ros2_ai_debugger.reporting import (
    AIStatus,
    Report,
    render_json,
    render_markdown,
    render_terminal,
)
from ros2_ai_debugger.utils.term import supports_color, supports_unicode

EXIT_OK, EXIT_FINDINGS, EXIT_ERROR = 0, 1, 2
GITHUB_DEFAULT = "github-report.md"


def add_arguments(p: argparse.ArgumentParser) -> None:
    ai = p.add_argument_group("AI analysis (off unless you choose one; nothing is ever sent by default)")
    ai.add_argument("--local", action="store_true",
                    help="analyze with a local Ollama model; data never leaves this machine")
    ai.add_argument("--provider", choices=sorted(PROVIDERS), help="cloud or local AI provider")
    ai.add_argument("--model", help="model name (default: provider-specific, or <PROVIDER>_MODEL env)")
    ai.add_argument("--no-ai", action="store_true", help="rule-based analysis only (the default)")
    ai.add_argument("--dry-run", action="store_true",
                    help="show exactly what would be sent to the AI provider, then exit without sending")
    ai.add_argument("--yes", action="store_true", help="do not ask before sending data to a cloud provider")
    priv = p.add_argument_group("privacy")
    priv.add_argument("--redact", action="store_true",
                      help="also mask hostnames, IPs, MACs, usernames, e-mails and home paths "
                           "(always on for Markdown reports; secrets are always scrubbed)")
    out = p.add_argument_group("output")
    out.add_argument("--output", "-o", metavar="FILE", help="write a report; format from extension (.md or .json)")
    out.add_argument("--github", action="store_true",
                     help=f"write a redacted, issue-ready Markdown report to {GITHUB_DEFAULT} "
                          "(no GitHub API is used)")
    out.add_argument("--format", choices=["text", "json", "markdown"], default="text",
                     help="format printed to stdout when --output is not used")
    out.add_argument("--no-color", action="store_true", help="disable colored output")
    out.add_argument("--fail-on", choices=["warning", "error"],
                     help="exit with status 1 if a finding of at least this severity exists")
    col = p.add_argument_group("collection and expectations")
    col.add_argument("--listen-seconds", type=float, default=2.0, metavar="S",
                     help="how long to listen to /tf, /diagnostics and /rosout (default: 2)")
    col.add_argument("--from-snapshot", metavar="FILE",
                     help="analyze a saved snapshot or JSON report instead of the live system")
    col.add_argument("--config", metavar="FILE", help="JSON file with expectations (see docs)")
    col.add_argument("--expect-node", action="append", default=[], metavar="NODE",
                     help="node that must be running (repeatable)")
    col.add_argument("--expect-domain-id", metavar="ID", help="expected ROS_DOMAIN_ID")
    col.add_argument("--watch-topic", action="append", default=[], metavar="TOPIC",
                     help="count messages on this topic (repeatable) to detect publishers that are silent. "
                          "Topics in the config's expected_publishers are watched automatically. Only the "
                          "message count is kept; payloads are never deserialized, stored or sent")


class UsageError(Exception):
    pass


def _validate(args: argparse.Namespace) -> None:
    if args.local and args.provider and args.provider != "ollama":
        raise UsageError("--local only works with Ollama; drop --provider or use --provider ollama")
    if args.no_ai and (args.local or args.provider or args.dry_run):
        raise UsageError("--no-ai cannot be combined with --local, --provider or --dry-run")
    if args.dry_run and not (args.local or args.provider):
        raise UsageError("--dry-run shows what would be sent to an AI provider; add --provider <name> or --local")
    if args.listen_seconds < 0:
        raise UsageError("--listen-seconds must be >= 0")
    if args.output and not args.output.lower().endswith((".md", ".json")):
        raise UsageError("--output must end in .md or .json")
    if args.github and args.output and not args.output.lower().endswith(".md"):
        raise UsageError("--github writes Markdown; use a .md file name")


def _load_snapshot(path: str) -> SystemSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SystemSnapshot.from_dict(data.get("snapshot", data))


def _select_provider(args, provider_factory) -> AIProvider | None:
    if args.local:
        return provider_factory("ollama", args.model, require_local=True)
    if args.provider:
        return provider_factory(args.provider, args.model)
    return None


def _default_provider_factory(name: str, model: str | None, **kw) -> AIProvider:
    return get_provider(name, model, **kw)


def _default_backend_factory(listen_seconds: float):
    from ros2_ai_debugger.collectors.rclpy_backend import RclpyBackend

    return RclpyBackend(listen_seconds=listen_seconds)


def run_diagnose(
    args: argparse.Namespace,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    backend_factory: Callable[[float], object] = _default_backend_factory,
    provider_factory: Callable[..., AIProvider] = _default_provider_factory,
    confirm: Callable[[str], bool] | None = None,
) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    try:
        _validate(args)
        config = ExpectedConfig.from_file(args.config) if args.config else ExpectedConfig()
    except (UsageError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=err)
        return EXIT_ERROR
    config.required_nodes += args.expect_node
    if args.expect_domain_id is not None:
        config.expected_domain_id = args.expect_domain_id

    # 1. Collect ---------------------------------------------------------
    try:
        if args.from_snapshot:
            raw = _load_snapshot(args.from_snapshot)
        else:
            print("Collecting ROS 2 diagnostics (read-only)...", file=err)
            with backend_factory(args.listen_seconds) as backend:
                watch = sorted(set(args.watch_topic) | set(config.expected_publishers))
                raw = collect_snapshot(default_collectors(backend, watch_topics=watch))
    except ImportError as exc:  # pragma: no cover - depends on environment
        print(f"error: {exc}", file=err)
        return EXIT_ERROR
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: cannot load snapshot: {exc}" if args.from_snapshot else f"error: {exc}", file=err)
        return EXIT_ERROR
    except RuntimeError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_ERROR

    # 2. Sanitize: everything downstream (rules, AI, report) sees only this copy
    md_output = bool(args.github) or bool(args.output and args.output.lower().endswith(".md")) \
        or (not args.output and args.format == "markdown")
    mask = args.redact or md_output
    snapshot = Redactor(mask, hostname=raw.environment.hostname).snapshot(raw)

    # 3. Rule-based analysis (always) --------------------------------------
    rule_findings = analyze(snapshot, config)
    report = Report(snapshot=snapshot, rule_findings=rule_findings, redacted=mask)

    # 4. Optional AI analysis --------------------------------------------
    provider = None
    try:
        provider = _select_provider(args, provider_factory)
    except ProviderError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_ERROR
    if provider is not None:
        rc = _ai_stage(args, provider, report, mask, out, err, confirm)
        if rc is not None:
            return rc

    # 5. Render ---------------------------------------------------------------
    return _emit(args, report, out, err, md_output)


def _ai_stage(args, provider, report: Report, mask: bool, out, err, confirm) -> int | None:
    """Returns an exit code to stop early (dry-run), or None to continue."""
    payload = build_payload(report.snapshot, report.rule_findings)
    summary = summarize_payload(payload, mask)
    if args.dry_run:
        print(f"DRY RUN: nothing is sent. Provider: {provider.describe()}", file=out)
        print("This is what would be transmitted:", file=out)
        print("".join(f"  {ln}\n" for ln in summary.lines()), file=out, end="")
        print("\n--- SYSTEM PROMPT ---", file=out)
        print(SYSTEM_PROMPT, file=out)
        print("--- USER MESSAGE ---", file=out)
        print(build_user_prompt(payload), file=out)
        return EXIT_OK
    report.ai = AIStatus(mode="disabled", provider=provider.name)
    if not provider.is_configured():
        report.ai.mode, report.ai.detail = "failed", f"provider not configured ({provider.config_help()})"
        print(f"warning: {report.ai.detail}; continuing with rule-based results only.", file=err)
        return None
    if not provider.is_local:
        print(f"About to send diagnostic data to {provider.describe()}:", file=err)
        for ln in summary.lines():
            print(f"  {ln}", file=err)
        print("  Preview the exact payload first with --dry-run.", file=err)
        if not args.yes:
            ask = confirm or _ask_tty
            if not ask("Send this data? [y/N] "):
                report.ai.mode = "declined"
                report.ai.detail = ("not confirmed" if sys.stdin.isatty() or confirm
                                    else "non-interactive session; pass --yes to allow sending")
                print(f"AI analysis skipped: {report.ai.detail}.", file=err)
                return None
    print(f"Analyzing with {provider.describe()}...", file=err)
    try:
        result = provider.analyze(report.snapshot, report.rule_findings)
    except (ProviderError, AIResponseError) as exc:
        report.ai.mode, report.ai.detail = "failed", str(exc)
        print(f"warning: AI analysis failed: {exc}", file=err)
        return None
    report.ai = AIStatus("used", provider.name, provider.describe(), result.summary,
                         result.missing_information, result.warnings)
    report.ai_findings = result.findings
    return None


def _ask_tty(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _emit(args, report: Report, out, err, md_output: bool) -> int:
    path = args.output or (GITHUB_DEFAULT if args.github else None)
    if path:
        text = render_json(report) if path.lower().endswith(".json") else render_markdown(report)
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {path}: {exc}", file=err)
            return EXIT_ERROR
        print(f"Report written to {path}  ({report.overall_label()}, {len(report.findings)} finding(s))", file=out)
    elif args.format == "json":
        out.write(render_json(report))
    elif args.format == "markdown":
        out.write(render_markdown(report))
    else:
        out.write(render_terminal(report, supports_color(out, args.no_color), supports_unicode(out)))
    if args.fail_on:
        limit = Severity.parse(args.fail_on)
        if any(f.severity >= limit for f in report.findings):
            return EXIT_FINDINGS
    return EXIT_OK
