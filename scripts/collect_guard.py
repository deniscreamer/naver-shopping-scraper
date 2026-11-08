"""The run rules around collecting one product (the owner's rules, 2026-11-05, as in the naver-harvester).

`collect(row)` returns an Outcome: complete, partial (with a reason and the error), or not taken (a card not found
on the listing: not a defect of the product). It raises SourceStopped for a captcha, a 418 / 429 or a login wall
(the API's 503, or its 502 "blocked the request"), a busy adapter (409) or a refused image CDN: the whole source
stops and no product is marked.

  * partial -> one more attempt; partial again -> the product is deferred in the shop's journal (deferred_log)
    with the reason and the first error;
  * two products in a row (different ones) ending partial for the same reason stop the run (RunStopped): that is
    a defect of the collector, not of the products;
  * a product with the owner's retry allowance spends it on this attempt: "retried" is written first, then a new
    "deferred" if it came out partial again.

    guard = CollectGuard(DeferredLog(store.id.value))
    outcome = guard.run(key, lambda: collect(row))     # raises SourceStopped / RunStopped
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from deferred_log import DeferredLog


class SourceStopped(Exception):
    """A captcha, 418 / 429 or a login wall: stop the source, mark no product. `status` / `error`: the API's answer
    (None for a refused image CDN), so a job can tell a wall from a busy adapter or Naver's error page."""

    def __init__(self, message: str, status: int | None = None, error: Any = None):
        super().__init__(message)
        self.status, self.error = status, error


class RunStopped(Exception):
    """Two products in a row came out partial for the same reason: the collector is at fault."""


@dataclass
class Outcome:
    status: str                              # complete | partial | not_taken | deferred
    reason: str | None = None                # partial / not_taken: a short code, e.g. "specs_missing"
    error: Any = None                        # partial: what went wrong (a message, a status)
    data: Any = None                         # what was collected (also for a partial one)
    attempts: int = 1
    first: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def partial(cls, reason: str, error: Any = None, data: Any = None) -> "Outcome":
        return cls("partial", reason, error, data)


class CollectGuard:
    def __init__(self, journal: DeferredLog):
        self.journal = journal
        self.last_partial: tuple[str, str] | None = None        # (key, reason) of the previous product

    def run(self, key: str, collect: Callable[[], Outcome]) -> Outcome:
        allowed = self.journal.retry_allowed(key)
        outcome = collect()
        first: dict[str, Any] | None = None
        if outcome.status == "partial":
            first = {"reason": outcome.reason, "error": outcome.error}
            outcome = collect()
            outcome.attempts, outcome.first = 2, first
            if outcome.status == "partial":
                outcome.status = "deferred"
        if allowed:                                  # spend the allowance before a new deferral is written
            self.journal.retried(key, outcome.status)
        if outcome.status == "deferred":
            self.journal.defer(key, outcome.reason or "partial", first)
            if self.last_partial and self.last_partial[0] != key and self.last_partial[1] == outcome.reason:
                raise RunStopped(f"two products in a row partial for {outcome.reason!r}: "
                                 f"{self.last_partial[0]}, {key}")
            self.last_partial = (key, outcome.reason or "partial")
        elif outcome.status == "complete":
            self.last_partial = None
        return outcome
