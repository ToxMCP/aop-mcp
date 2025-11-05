"""Lightweight metrics recorder for adapters and services."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter
from typing import Dict


class MetricsRecorder:
    def __init__(self) -> None:
        self.counters: Dict[str, int] = defaultdict(int)
        self.timings: Dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    @contextmanager
    def time(self, name: str):
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self.timings[name].append(elapsed)

