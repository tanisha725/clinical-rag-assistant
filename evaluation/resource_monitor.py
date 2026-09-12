"""Samples `docker stats` for a container on a background thread for the
duration of one generation call, so latency-sensitive code isn't blocked."""
import re
import subprocess
import threading
import time


def _parse_mem_mib(mem_str: str) -> float:
    # docker stats MemUsage looks like "123.4MiB / 914MiB"
    value = mem_str.split("/")[0].strip()
    match = re.match(r"([\d.]+)\s*(MiB|GiB|KiB)", value)
    if not match:
        return 0.0
    num, unit = float(match.group(1)), match.group(2)
    return num * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[unit]


def _parse_cpu_pct(cpu_str: str) -> float:
    return float(cpu_str.strip().rstrip("%") or 0.0)


class ResourceMonitor:
    def __init__(self, container_name: str, interval_seconds: float = 0.5, ssh_prefix: list[str] | None = None):
        self.container_name = container_name
        self.interval_seconds = interval_seconds
        self.ssh_prefix = ssh_prefix or []
        self._samples: list[tuple[float, float]] = []  # (cpu_pct, mem_mib)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_once(self):
        cmd = self.ssh_prefix + [
            "sudo", "docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", self.container_name,
        ]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
            cpu_str, mem_str = out.split("|")
            self._samples.append((_parse_cpu_pct(cpu_str), _parse_mem_mib(mem_str)))
        except Exception:
            pass

    def _run(self):
        while not self._stop_event.is_set():
            self._sample_once()
            self._stop_event.wait(self.interval_seconds)

    def start(self):
        self._samples = []
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if not self._samples:
            return {"cpu_avg": None, "cpu_peak": None, "mem_avg_mib": None, "mem_peak_mib": None, "samples": 0}
        cpus = [s[0] for s in self._samples]
        mems = [s[1] for s in self._samples]
        return {
            "cpu_avg": sum(cpus) / len(cpus),
            "cpu_peak": max(cpus),
            "mem_avg_mib": sum(mems) / len(mems),
            "mem_peak_mib": max(mems),
            "samples": len(self._samples),
        }
