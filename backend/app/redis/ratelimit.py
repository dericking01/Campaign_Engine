"""GCRA (leaky-bucket via theoretical-arrival-time) rate limiter enforcing
the hard global 200 TPS ceiling plus each channel's sub-allocation - see
docs/architecture.md Redis section. This replaces the legacy scripts'
uncoordinated self-throttling (each of smsmaster.php/ivrmaster.php/
drmaster.php independently tried to hit its own target TPS with no
awareness of the others, so the combined load could exceed what the real
SMSC could sustain).

One atomic Lua script checks the channel limiter and the global limiter
together and only commits state to either if BOTH would pass - avoids the
bug of consuming a global token, then discovering the channel is exhausted
(or vice versa) with no way to "give back" the wrongly-consumed token.

A single float TAT (theoretical arrival time) per limiter key is
self-correcting after a Redis restart or a lost/expired key: an absent key
is treated as "start now", not as "quota already gone" - worst case is a
brief burst right after a restart, never a permanent wedge. This is a
deliberate, documented trade-off (see docs/decisions.md), not an oversight.
"""

import time

import redis

from app.core.config import get_settings

settings = get_settings()

_KEY_TTL_SECONDS = 30  # self-expires when idle; never the source of truth

_GCRA_SCRIPT = """
local function check(key, rate, burst, now)
    local emission_interval = 1.0 / rate
    local burst_offset = emission_interval * burst
    local tat = tonumber(redis.call('GET', key))
    if tat == nil then
        tat = now
    end
    tat = math.max(tat, now)
    local allow_at = tat - burst_offset
    if now >= allow_at then
        return tostring(tat + emission_interval)
    else
        return nil
    end
end

local now = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])

local new_channel_tat = check(KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), now)
if new_channel_tat == nil then
    return 0
end

local new_global_tat = check(KEYS[2], tonumber(ARGV[3]), tonumber(ARGV[4]), now)
if new_global_tat == nil then
    return 0
end

redis.call('SET', KEYS[1], new_channel_tat, 'EX', ttl)
redis.call('SET', KEYS[2], new_global_tat, 'EX', ttl)
return 1
"""

_CHANNEL_TPS = {
    "SMS": settings.sms_tps_allocation,
    "IVR": settings.ivr_tps_allocation,
    "DOCTOR": settings.doctor_tps_allocation,
}

_client: redis.Redis | None = None
_script_sha: str | None = None


def _get_client() -> redis.Redis:
    global _client, _script_sha
    if _client is None:
        _client = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)
        _script_sha = _client.script_load(_GCRA_SCRIPT)
    return _client


def try_acquire(channel: str) -> bool:
    """Non-blocking: returns True iff both the channel sub-allocation and
    the global 200 TPS ceiling have room for one more dispatch attempt
    right now. Burst capacity is deliberately 0 (strict pacing, one
    request per 1/rate-second slot, no allowance beyond that) - this is
    the single most important knob in this file, so the reasoning is
    worth spelling out:

    GCRA's standard convention of burst == rate (capacity == rate,
    refill == rate/sec) was tried first and measured live: on a cold key
    it let a full extra second's worth of requests through immediately
    (a one-time "bucket starts full" allowance), and because that excess
    only amortizes away as the measurement window -> infinity, a 5-second
    continuous hammer still ran at 169/s against a 140/s configured rate
    (real measurement, not a calculation) - i.e. for any campaign run of
    realistic duration, "burst == rate" does NOT converge to the
    configured ceiling, it just moves the overshoot around. Since this
    ceiling exists specifically to never again exceed what the real SMSC
    can sustain (see docs/decisions.md - the whole reason this rewrite
    exists), a ceiling that can run 20%+ hot for the entire duration of a
    run is not a hard ceiling. Burst=0 trades that away for strict,
    unconditional pacing: every dispatch attempt, including the very
    first one after an idle period, waits its exact turn.
    """
    client = _get_client()
    channel_rate = _CHANNEL_TPS[channel]
    now = time.time()
    result = client.evalsha(
        _script_sha,
        2,
        f"campaign:ratelimit:channel:{channel.lower()}:tat",
        "campaign:ratelimit:global:tat",
        channel_rate,
        0,
        settings.global_tps_limit,
        0,
        now,
        _KEY_TTL_SECONDS,
    )
    return bool(result)


def acquire_blocking(channel: str, max_wait_seconds: float = 5.0) -> bool:
    """Polls try_acquire with a short sleep until a slot opens or
    max_wait_seconds elapses. Used by dispatch workers so a momentary
    ceiling-saturation doesn't fail the message outright - it just waits
    its turn, same as a customer's SMS waiting in any rate-limited queue.
    Returns False if no slot opened within the deadline (caller should
    treat this as transient and retry later via the normal RETRYING path,
    not as a delivery failure)."""
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if try_acquire(channel):
            return True
        time.sleep(0.02)
    return False
