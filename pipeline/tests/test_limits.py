from bse_intel.ai.limits import Limits, QuotaCounter, RateLimiter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def test_scaled_applies_95_percent_ceiling():
    lim = Limits(rpm=30, tpm=6000, rpd=14400, tpd=500000).scaled(0.95)
    assert (lim.rpm, lim.tpm, lim.rpd, lim.tpd) == (28, 5700, 13680, 475000)
    assert Limits(rpm=1).scaled(0.95).rpm == 1


def test_rpm_pacing_waits_for_window():
    clock = Clock()
    limiter = RateLimiter(Limits(rpm=2), clock=clock, sleep=clock.sleep)
    assert limiter.acquire(10) and limiter.acquire(10)
    start = clock.t
    assert limiter.acquire(10, max_wait=90)
    assert clock.t - start >= 59.9


def test_rpm_pacing_gives_up_when_wait_too_long():
    clock = Clock()
    limiter = RateLimiter(Limits(rpm=1), clock=clock, sleep=clock.sleep)
    assert limiter.acquire(10)
    assert not limiter.acquire(10, max_wait=5)


def test_tpm_budget_and_oversized_request():
    clock = Clock()
    limiter = RateLimiter(Limits(tpm=1000), clock=clock, sleep=clock.sleep)
    assert limiter.acquire(800)
    assert not limiter.acquire(5000, max_wait=120)  # can never fit
    assert limiter.acquire(800, max_wait=120)       # waits for the first to expire


def test_daily_quota_and_settle():
    quota = QuotaCounter(Limits(tpd=1000))
    limiter = RateLimiter(Limits(tpd=1000), quota)
    assert limiter.acquire(600)
    limiter.settle(600, 200)
    assert quota.day_tokens == 200
    assert limiter.acquire(700)
    assert not limiter.acquire(200)
    assert quota.exhausted(200) == "daily token ceiling"
    assert 0.89 < quota.utilisation() <= 0.9
