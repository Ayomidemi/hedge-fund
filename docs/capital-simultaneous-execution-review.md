# Capital simultaneous execution — 8 October 2026

Capital supports multiple pending orders and open positions. Each cycle evaluates
all existing exits and pending entries, then queues qualifying new signals.
New entries do not wait for another position to close. Financial updates remain
serialized under the account lock to prevent double spending.

The observed account was Automatic / High, with an eight-position ceiling,
one open DFNS position and one closed PMI position. Its recorded blocker was an
outdated DFNS quote. A separate read-only provider request returned a fresh DFNS
reference price. Worker logs also showed a 199-second execution task and an
account-lock statement timeout; database diagnostics confirmed blocked writes
and long-lived transactions whose last query loaded risk history.

## Changes

- Consistent radar ordering for history loading and order selection. A regression
  reproduced missing instrument metadata when two scan start times tied.
- Each execution cycle has a 60-second client deadline, a five-second database
  lock timeout, and a 60-second idle transaction timeout. Interrupted work rolls
  back. Existing account locking, limits and idempotent ledger booking remain.
- History queries retrieve the prices, volume and provider close field used by
  risk calculations, omitting full vendor payloads and unrelated bar fields.
- Stale holding messages explicitly explain that new buys are also paused.
- Dashboard and opportunity queue show used versus maximum position slots;
  blocked-entry details remain visible when another position is already open.

## Verification

- 346 unit tests passed.
- 40 PostgreSQL integration/migration tests passed in disposable schemas.
- New tests verify two entries fill in one cycle, a third opens while both remain
  held, one exits independently, competing cycles do not duplicate fills, and
  booked cash and position counts agree.
- A stalled history read times out, rolls back and allows another session to
  acquire the account lock. History projection preserves required price fields.
- TypeScript, full frontend lint and 20 UI render scenarios passed.

These tests establish execution behavior, not expected returns. Every additional
entry still requires valid quotes, qualifying signals, sufficient history, cash,
and risk capacity. No account reset or risk-profile change was performed.
