"""Host resources and ROS-related environment (stdlib + /proc only)."""
from __future__ import annotations

import fcntl
import os
import platform
import shutil
import socket
import struct
import time
from pathlib import Path

from ros2_ai_debugger.collectors.base import DiagnosticCollector
from ros2_ai_debugger.models import EnvironmentInfo, NetworkInterfaceInfo, SystemResourceInfo

#: The ONLY environment variables ever read. Arbitrary env vars are never collected.
ENV_WHITELIST = (
    "ROS_DISTRO",
    "ROS_DOMAIN_ID",
    "RMW_IMPLEMENTATION",
    "ROS_LOCALHOST_ONLY",
)


class EnvironmentCollector(DiagnosticCollector):
    name, field = "environment", "environment"

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._env = os.environ if environ is None else environ

    def collect(self) -> EnvironmentInfo:
        return EnvironmentInfo(
            ros_distro=self._env.get("ROS_DISTRO"),
            ros_domain_id=self._env.get("ROS_DOMAIN_ID"),
            rmw_implementation=self._env.get("RMW_IMPLEMENTATION"),
            localhost_only=self._env.get("ROS_LOCALHOST_ONLY"),
            os_name=_os_name(),
            python_version=platform.python_version(),
            hostname=socket.gethostname(),
        )


def _os_name() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def parse_cpu_times(stat_line: str) -> tuple[int, int]:
    """Return (idle, total) jiffies from the aggregate ``cpu`` line of /proc/stat."""
    fields = [int(x) for x in stat_line.split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)  # idle + iowait
    return idle, sum(fields[:8])


def parse_meminfo(text: str) -> tuple[float, int] | None:
    """Return (used percent, total MB) using MemAvailable, or None if unavailable."""
    kv = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            kv[key] = int(parts[0])
    if "MemTotal" not in kv or "MemAvailable" not in kv or kv["MemTotal"] == 0:
        return None
    used = 100.0 * (kv["MemTotal"] - kv["MemAvailable"]) / kv["MemTotal"]
    return round(used, 1), kv["MemTotal"] // 1024


def _cpu_percent(interval: float) -> float | None:
    try:
        i1, t1 = parse_cpu_times(Path("/proc/stat").read_text().splitlines()[0])
        time.sleep(interval)
        i2, t2 = parse_cpu_times(Path("/proc/stat").read_text().splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None
    return round(100.0 * (1 - (i2 - i1) / (t2 - t1)), 1) if t2 > t1 else None


def _ipv4(ifname: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            packed = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", ifname[:15].encode()))
        return socket.inet_ntoa(packed[20:24])
    except OSError:
        return ""


def _network() -> list[NetworkInterfaceInfo]:
    out = []
    base = Path("/sys/class/net")
    try:
        names = sorted(p.name for p in base.iterdir())
    except OSError:
        return out

    def stat(name: str, key: str) -> int:
        try:
            return int((base / name / "statistics" / key).read_text())
        except (OSError, ValueError):
            return 0

    for name in names:
        try:
            state = (base / name / "operstate").read_text().strip()
        except OSError:
            state = ""
        out.append(
            NetworkInterfaceInfo(
                name=name,
                state=state,
                ipv4=_ipv4(name),
                rx_bytes=stat(name, "rx_bytes"),
                tx_bytes=stat(name, "tx_bytes"),
                rx_errors=stat(name, "rx_errors"),
                tx_errors=stat(name, "tx_errors"),
            )
        )
    return out


class SystemCollector(DiagnosticCollector):
    name, field = "system", "system"

    def __init__(self, cpu_interval: float = 0.3, disk_path: str = "/") -> None:
        self._interval = cpu_interval
        self._disk = disk_path

    def collect(self) -> SystemResourceInfo:
        info = SystemResourceInfo(cpu_count=os.cpu_count() or 0, disk_path=self._disk)
        info.cpu_percent = _cpu_percent(self._interval)
        try:
            info.load_avg = [round(x, 2) for x in os.getloadavg()]
        except OSError:
            pass
        try:
            mem = parse_meminfo(Path("/proc/meminfo").read_text())
            if mem:
                info.memory_percent, info.memory_total_mb = mem
        except OSError:
            pass
        try:
            du = shutil.disk_usage(self._disk)
            info.disk_percent = round(100.0 * du.used / du.total, 1)
        except OSError:
            pass
        info.network = _network()
        return info
