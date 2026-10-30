"""Adaptive Rate Limiting & Backoff Engine for Osintgram.

Controls request pacing with jitter, reading breaks, and adaptive backoff
during bulk pagination on private API backends (followers, followings,
comments, feeds) to respect Instagram rate limits and handle throttling gracefully.
"""
import configparser
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path("config/credentials.ini")


class PacingMode:
    CONSERVATIVE = "conservative"  # Slower pacing with reading breaks and backoff
    NORMAL = "normal"              # Balanced pacing matching baseline instagrapi delays (1.2-2.6s)
    FAST = "fast"                  # Minimal delays; high risk of Instagram action blocks
    CUSTOM = "custom"



@dataclass
class PacingConfig:
    mode: str = PacingMode.NORMAL
    min_delay: float = 1.2
    max_delay: float = 2.6
    break_frequency: int = 25      # requests between reading breaks
    break_min: float = 10.0        # reading break min duration (seconds)
    break_max: float = 20.0        # reading break max duration (seconds)
    adaptive_backoff: bool = True  # back off on rate-limit warnings


def resolve_pacing_config() -> PacingConfig:
    """Resolve pacing configuration from environment or credentials.ini."""
    env_mode = (
        os.getenv("SCRAPE_PACING") or os.getenv("OSINTGRAM_PACING") or ""
    ).strip().lower()

    cfg = PacingConfig()
    if CREDENTIALS_PATH.exists():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(CREDENTIALS_PATH, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read credentials file %s: %s", CREDENTIALS_PATH, e)

        if parser.has_section("Pacing"):
            sec = parser["Pacing"]

            if "mode" in sec:
                raw_mode = sec.get("mode", "").strip().lower()
                if raw_mode in (
                    PacingMode.CONSERVATIVE,
                    PacingMode.NORMAL,
                    PacingMode.FAST,
                    PacingMode.CUSTOM,
                ):
                    cfg.mode = raw_mode
                else:
                    logger.warning("Invalid pacing mode in credentials.ini: %r", raw_mode)

            if "min_delay" in sec:
                try:
                    val = float(sec.get("min_delay"))
                    if val >= 0:
                        cfg.min_delay = val
                    else:
                        logger.warning("Invalid min_delay in credentials.ini: %s", sec.get("min_delay"))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse min_delay in credentials.ini: %s", e)

            if "max_delay" in sec:
                try:
                    val = float(sec.get("max_delay"))
                    if val >= 0:
                        cfg.max_delay = val
                    else:
                        logger.warning("Invalid max_delay in credentials.ini: %s", sec.get("max_delay"))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse max_delay in credentials.ini: %s", e)

            if "break_frequency" in sec:
                try:
                    val = int(sec.get("break_frequency"))
                    if val >= 0:
                        cfg.break_frequency = val
                    else:
                        logger.warning("Invalid break_frequency in credentials.ini: %s", sec.get("break_frequency"))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse break_frequency in credentials.ini: %s", e)

            if "break_min" in sec:
                try:
                    val = float(sec.get("break_min"))
                    if val >= 0:
                        cfg.break_min = val
                    else:
                        logger.warning("Invalid break_min in credentials.ini: %s", sec.get("break_min"))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse break_min in credentials.ini: %s", e)

            if "break_max" in sec:
                try:
                    val = float(sec.get("break_max"))
                    if val >= 0:
                        cfg.break_max = val
                    else:
                        logger.warning("Invalid break_max in credentials.ini: %s", sec.get("break_max"))
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse break_max in credentials.ini: %s", e)

            if "adaptive_backoff" in sec:
                try:
                    cfg.adaptive_backoff = sec.getboolean("adaptive_backoff")
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse adaptive_backoff in credentials.ini: %s", e)

            if cfg.min_delay > cfg.max_delay:
                cfg.max_delay = cfg.min_delay
            if cfg.break_min > cfg.break_max:
                cfg.break_max = cfg.break_min

    valid_modes = (
        PacingMode.CONSERVATIVE,
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
        """Compute delay duration using Gaussian distribution with bounded clipping."""
        if not is_subsequent or self.config.mode == PacingMode.FAST:
            return 0.05

        mode = self.config.mode
        if mode == PacingMode.CONSERVATIVE:
            low = 2.0
            high = 4.8
            mean = 3.2
            std_dev = 0.7
        elif mode == PacingMode.CUSTOM:
            low = max(0.01, self.config.min_delay)
            high = max(low, self.config.max_delay)
            mean = (low + high) / 2.0
            std_dev = max(0.1, (high - low) / 4.0)
        else:  # NORMAL
            # Baseline conservative range (1.2s - 2.6s, mean 1.85s)
            low = 1.2
            high = 2.6
            mean = 1.85
            std_dev = 0.35

        # Gaussian random with realistic clipping
        delay = random.gauss(mean, std_dev)
        delay = max(low, min(high, delay))

        # Check if a reading break is due
        break_freq = self.config.break_frequency
        if (
            break_freq > 0
            and self.request_count > 0
            and (self.request_count % break_freq == 0)
        ):
            if mode == PacingMode.CONSERVATIVE:
                break_duration = random.uniform(
                    self.config.break_min, self.config.break_max
                )
            else:
                break_duration = random.uniform(3.0, 6.0)
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


_SHARED_PACER: Optional[HumanPacer] = None


def get_shared_pacer() -> HumanPacer:
    """Return the global shared pacer instance to preserve throttle/backoff state across scans."""
    global _SHARED_PACER
    if _SHARED_PACER is None:
        _SHARED_PACER = HumanPacer()
    return _SHARED_PACER


def reset_shared_pacer() -> None:
    """Reset the global shared pacer (for test isolation)."""
    global _SHARED_PACER
    _SHARED_PACER = None
