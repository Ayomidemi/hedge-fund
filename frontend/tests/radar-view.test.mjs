import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../src/lib/radar-view.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const loaded = { exports: {} };
new Function('exports', 'module', compiled)(loaded.exports, loaded);
const { filterRadarNames, hasDataGap } = loaded.exports;
const name = (ticker, extra = {}) => ({ ticker, name: ticker, jurisdiction: 'US', industry: 'Software',
  radar_priority: 'P1', evidence: { return_sample_count: 30 }, ...extra });
const options = { market: 'all', industry: '', query: '', view: 'all', sort: 'priority' };
const tickers = (names, overrides = {}) => filterRadarNames(names, { ...options, ...overrides }).map(n => n.ticker);

test('priority signals exclude stale and carried observations', () => {
  const rows = [name('STALE', { stale_reason: 'old', radar_priority: 'P0' }),
    name('CARRIED', { carried_forward: true }), name('VALID'), name('LOW', { radar_priority: 'P3' })];
  assert.deepEqual(tickers(rows, { view: 'signals' }), ['VALID']);
  assert.deepEqual(rows.map(r => r.ticker), ['STALE', 'CARRIED', 'VALID', 'LOW']);
});
test('unknown prices sort last in both directions, including invalid numbers', () => {
  const rows = [name('MISSING', { change_pct: null }), name('BAD', { change_pct: 'NaN' }),
    name('RISE', { change_pct: '5' }), name('FALL', { change_pct: '-3' }), name('FLAT', { change_pct: '0' })];
  assert.deepEqual(tickers(rows, { sort: 'gainers' }), ['RISE', 'FLAT', 'FALL', 'BAD', 'MISSING']);
  assert.deepEqual(tickers(rows, { sort: 'losers' }), ['FALL', 'FLAT', 'RISE', 'BAD', 'MISSING']);
});
test('market, industry, text and held/watchlist filters combine', () => {
  const rows = [name('US', { name: 'Alpha', on_watchlist: true }),
    name('NG', { name: 'Alpha', jurisdiction: 'NG', on_watchlist: true }),
    name('HELD', { in_portfolio: true }), name('OTHER')];
  assert.deepEqual(tickers(rows, { market: 'US', industry: 'US:Software', query: ' ALPHA ', view: 'watched' }), ['US']);
  assert.deepEqual(tickers(rows, { market: 'US', view: 'watched' }), ['HELD', 'US']);
});
test('missing or short history and carried observations remain visible as data gaps', () => {
  assert.equal(hasDataGap(name('READY')), false);
  for (const extra of [{ evidence: {} }, { evidence: { return_sample_count: 19 } },
    { evidence: { return_sample_count: 30, history_gap: true } }, { carried_forward: true }]) {
    assert.equal(hasDataGap(name('GAP', extra)), true);
  }
});
