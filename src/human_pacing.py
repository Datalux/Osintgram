"""Human Emulation & Anti-Throttling Pacing Engine for Osintgram.

Simulates authentic human browsing behavior during bulk pagination (followers,
followings, comments, post feeds) to evade bot heuristics, Instagram
feedback_required action blocks, and rate limit triggers.
"""
import configparser
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

CREDENTIALS_PATH = Path("config/credentials.ini")


class PacingMode:
    STEALTH = "stealth"  # Slowest, highest human-realism (Gaussian + breaks)
    NORMAL = "normal"    # Balanced pacing with minor jitter
    FAST = "fast"        # Minimal delays, suitable for paid high-throughput
    CUSTOM = "custom"


@dataclass
class PacingConfig:
    mode: str = PacingMode.NORMAL
    min_delay: float = 1.5
    max_delay: float = 3.5
    break_frequency: int = 20      # requests between reading breaks
    break_min: float = 12.0        # reading break min duration (seconds)
    break_max: float = 22.0        # reading break max duration (seconds)
    adaptive_backoff: bool = True  # back off on rate-limit warnings


def resolve_pacing_config() -> PacingConfig:
    """Resolve pacing configuration from environment or credentials.ini."""
    env_mode = (
        os.getenv("SCRAPE_PACING") or os.getenv("OSINTGRAM_PACING") or ""
    ).strip().lower()

    cfg = PacingConfig()
    if CREDENTIALS_PATH.exists():
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(CREDENTIALS_PATH, encoding="utf-8")
            if parser.has_section("Pacing"):
                sec = parser["Pacing"]
                cfg.mode = sec.get("mode", fallback=cfg.mode).strip().lower()
                cfg.min_delay = float(
                    sec.get("min_delay", fallback=str(cfg.min_delay))
                )
                cfg.max_delay = float(
                    sec.get("max_delay", fallback=str(cfg.max_delay))
                )
                cfg.break_frequency = int(
                    sec.get(
                        "break_frequency", fallback=str(cfg.break_frequency)
                    )
                )
                cfg.break_min = float(
                    sec.get("break_min", fallback=str(cfg.break_min))
                )
                cfg.break_max = float(
                    sec.get("break_max", fallback=str(cfg.break_max))
                )
        except Exception:
            pass

    valid_modes = (
        PacingMode.STEALTH,
        PacingMode.NORMAL,
        PacingMode.FAST,
        PacingMode.CUSTOM,
    )
    if env_mode in valid_modes:
        cfg.mode = env_mode

    return cfg


class HumanPacer:
    """Controls request pacing with Gaussian jitter, reading breaks,
    and adaptive backoff.
    """

    def __init__(
        self,
        config: Optional[PacingConfig] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        self.config = config or resolve_pacing_config()
        self.sleep_fn = sleep_fn or time.sleep
        self.request_count: int = 0
        self.consecutive_errors: int = 0
        self.total_delays_sec: float = 0.0
        self.reading_breaks_taken: int = 0
        self.last_delay: float = 0.0
        self.is_on_break: bool = False

    def compute_delay(self, is_subsequent: bool = True) -> float:
        """Compute human-like delay duration using Gaussian distribution with
        bounded clipping.
        """
        if not is_subsequent or self.config.mode == PacingMode.FAST:
            return 0.05

        mode = self.config.mode
        if mode == PacingMode.STEALTH:
            mean = 2.8
            std_dev = 0.7
            low = 1.6
            high = 4.8
        elif mode == PacingMode.CUSTOM:
            low = self.config.min_delay
            high = self.config.max_delay
            mean = (low + high) / 2.0
            std_dev = max(0.1, (high - low) / 4.0)
        else:  # NORMAL
            mean = 1.4
            std_dev = 0.35
            low = 0.8
            high = 2.4

        # Gaussian random with realistic right-tail clipping
        delay = random.gauss(mean, std_dev)
        delay = max(low, min(high, delay))

        # Check if a reading break is due
        break_freq = self.config.break_frequency
        if (
            break_freq > 0
            and self.request_count > 0
            and (self.request_count % break_freq == 0)
        ):
            if mode == PacingMode.STEALTH:
                break_duration = random.uniform(
                    self.config.break_min, self.config.break_max
                )
            else:
                break_duration = random.uniform(4.0, 8.0)
            delay += break_duration
            self.reading_breaks_taken += 1
            self.is_on_break = True
        else:
            self.is_on_break = False

        # Apply adaptive backoff if recent errors/throttles were observed
        if self.config.adaptive_backoff and self.consecutive_errors > 0:
            backoff_factor = min(4.0, 1.0 + (self.consecutive_errors * 0.75))
            delay *= backoff_factor

        return round(delay, 3)

    def pace(self, is_subsequent: bool = True) -> float:
        """Execute pacing sleep and record metrics."""
        self.request_count += 1
        delay = self.compute_delay(is_subsequent=is_subsequent)
        self.last_delay = delay
        self.total_delays_sec += delay
        if delay > 0:
            self.sleep_fn(delay)
        return delay

    def record_throttle_or_error(self) -> None:
        """Signal rate limiting or throttling symptoms."""
        self.consecutive_errors += 1

    def record_success(self) -> None:
        """Signal successful request; decays error backoff."""
        if self.consecutive_errors > 0:
            self.consecutive_errors -= 1

    def get_stats(self) -> Dict[str, Any]:
        """Return live telemetry of pacing operations."""
        return {
            "mode": self.config.mode,
            "requests_paced": self.request_count,
            "reading_breaks_taken": self.reading_breaks_taken,
            "total_delays_sec": round(self.total_delays_sec, 2),
            "last_delay_sec": self.last_delay,
            "throttle_level": self.consecutive_errors,
        }
