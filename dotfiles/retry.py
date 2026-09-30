"""Retrying what goes to the network: a policy and its attempts."""

import subprocess
from dataclasses import dataclass
from time import sleep

from dotfiles.engine import Report


@dataclass(frozen=True)
class RetryPolicy:
    """How often and how long apart retrying() tries again."""

    attempts: int = 3  # in total, the first one included
    delay: float = 10  # seconds before the second attempt
    backoff: float = 2  # each next delay is the previous one times this
    max_delay: float = 60  # no single wait longer than this
    # A command that failed; a missing program or a bug fails the same the next time.
    retry_on: tuple[type[Exception], ...] = (subprocess.CalledProcessError,)

    def wait(self, attempt: int) -> float:
        """Seconds to wait after failed attempt number ATTEMPT."""
        return min(self.delay * self.backoff ** (attempt - 1), self.max_delay)


# For anything that goes to the network: 3 attempts, 10 s then 20 s apart.
_NETWORK = RetryPolicy()


class Attempt:
    """One try of retrying(): a failure it swallows makes the loop go again."""

    def __init__(self, report: Report, policy: RetryPolicy, number: int):
        """Try NUMBER of POLICY; its warnings go to REPORT."""
        self.report = report
        self.policy = policy
        self.number = number
        self.failed = False

    def __enter__(self):
        """The attempt itself."""
        return self

    def __exit__(self, kind, error, traceback) -> bool:
        """Swallow a retryable error, warn and wait, unless it is the last attempt."""
        if error is None or not isinstance(error, self.policy.retry_on):
            return False
        if self.number == self.policy.attempts:
            return False
        what = error.cmd if isinstance(error, subprocess.CalledProcessError) else None
        what = " ".join(map(str, what)) if isinstance(what, list) else str(error)
        wait = self.policy.wait(self.number)
        self.report.warn(
            f"{what} failed (attempt {self.number}/{self.policy.attempts}), retrying in {wait:g}s"
        )
        sleep(wait)
        self.failed = True
        return True


def retrying(report: Report, policy: RetryPolicy = _NETWORK):
    """Attempts to run `with attempt:` until one succeeds; the last failure propagates."""
    for number in range(1, policy.attempts + 1):
        attempt = Attempt(report, policy, number)
        yield attempt
        if not attempt.failed:
            return
