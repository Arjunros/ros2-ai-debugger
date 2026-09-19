"""Redaction of sensitive data before it leaves the machine or enters a report.

Two levels:

* **Secret scrubbing** (always applied to anything sent to a cloud provider or
  written to a shareable report): API keys, bearer tokens, ``password=...``
  style assignments, private key blocks.
* **Identifier masking** (``--redact``, and always for Markdown reports):
  hostnames, IPv4/MAC addresses, e-mail addresses, the current username, and
  home-directory paths, replaced by stable placeholders (``<ip-1>``).

ROS graph names (nodes, topics, services) are intentionally kept: without
them a diagnosis is impossible.
"""
from __future__ import annotations

import getpass
import re

from ros2_ai_debugger.models import SystemSnapshot

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{8,}"),
    re.compile(r"(?i)\b(pass(?:word|wd)?|secret|token|api[_-]?key|credentials?|auth)\b(\s*[:=]\s*)\S+"),
]
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_HOME = re.compile(r"/(?:home|Users)/[^/\s'\"]+")
_SENSITIVE_KEYS = re.compile(r"(?i)serial|password|passwd|secret|token|key|credential|mac|uuid|imei")
MAX_MESSAGE_CHARS = 300


class Redactor:
    def __init__(self, mask_identifiers: bool = False, hostname: str = "", username: str | None = None):
        self.mask_identifiers = mask_identifiers
        self._hostname = hostname
        try:
            self._username = username if username is not None else getpass.getuser()
        except Exception:  # noqa: BLE001 - no passwd entry in some containers
            self._username = ""
        self._placeholders: dict[tuple[str, str], str] = {}

    def _placeholder(self, kind: str, value: str) -> str:
        key = (kind, value)
        if key not in self._placeholders:
            n = 1 + sum(1 for k in self._placeholders if k[0] == kind)
            self._placeholders[key] = f"<{kind}-{n}>"
        return self._placeholders[key]

    def text(self, value: str) -> str:
        """Scrub secrets and (optionally) identifiers from free text."""
        for pat in _SECRET_PATTERNS[:-1]:
            value = pat.sub("<redacted-secret>", value)
        value = _SECRET_PATTERNS[-1].sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted-secret>", value)
        if self.mask_identifiers:
            value = _EMAIL.sub(lambda m: self._placeholder("email", m.group(0)), value)
            value = _IPV4.sub(lambda m: self._placeholder("ip", m.group(0)), value)
            value = _MAC.sub(lambda m: self._placeholder("mac", m.group(0)), value)
            value = _HOME.sub("/home/<user>", value)
            for word, label in ((self._hostname, "host"), (self._username, "user")):
                if len(word) >= 3:
                    value = re.sub(rf"\b{re.escape(word)}\b", f"<{label}>", value)
        return value[:MAX_MESSAGE_CHARS] + "..." if len(value) > MAX_MESSAGE_CHARS else value

    def snapshot(self, snap: SystemSnapshot) -> SystemSnapshot:
        """Return a redacted deep copy; the input is not modified."""
        out = SystemSnapshot.from_dict(snap.to_dict())
        r = self.text
        out.collection_errors = [r(e) for e in out.collection_errors]
        for log in out.logs:
            log.message = r(log.message)
        for d in out.diagnostics:
            d.message = r(d.message)
            d.hardware_id = self._mask_id(d.hardware_id)
            d.values = {
                k: ("<redacted>" if _SENSITIVE_KEYS.search(k) else r(v)) for k, v in d.values.items()
            }
        if self.mask_identifiers:
            out.environment.hostname = "<host>" if out.environment.hostname else ""
            if out.system:
                for i, nic in enumerate(out.system.network, 1):
                    nic.ipv4 = self._placeholder("ip", nic.ipv4) if nic.ipv4 else ""
        return out

    def _mask_id(self, value: str) -> str:
        return self._placeholder("hw", value) if (value and self.mask_identifiers) else value


def make_redactor(snap: SystemSnapshot, mask_identifiers: bool) -> Redactor:
    return Redactor(mask_identifiers, hostname=snap.environment.hostname)
