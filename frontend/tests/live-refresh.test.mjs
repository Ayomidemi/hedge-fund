import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';

import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/lib/live-refresh.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const loaded = { exports: {} };
new Function('exports', 'module', compiled)(loaded.exports, loaded);
const { createLiveRefreshScheduler, shouldRefreshRoute } = loaded.exports;
function setup() {
  let visible = true, busy = false, count = 0, id = 0;
  const timers = new Map();
  const scheduler = createLiveRefreshScheduler({
    refresh: () => count++, visible: () => visible, busy: () => busy,
    schedule: (callback, delay) => { timers.set(++id, { callback, delay }); return id; },
    cancel: (id) => timers.delete(id),
  });
  return { scheduler, timers, count: () => count, visible: (v) => visible = v, busy: (v) => busy = v,
    fire: () => { const [id, task] = timers.entries().next().value; timers.delete(id); task.callback(); },
  };
}
test('event storms create one refresh per 30-second window', () => {
  const s = setup();
  for (let i = 0; i < 500; i++) s.scheduler.notify();
  assert.equal(s.timers.size, 1);
  assert.equal([...s.timers.values()][0].delay, 30000);
  s.fire(); assert.equal(s.count(), 1); assert.equal(s.timers.size, 0);
});
test('hidden tabs keep dirty state and resume when visible', () => {
  const s = setup(); s.scheduler.notify(); s.visible(false); s.fire();
  assert.equal(s.count(), 0); s.scheduler.notify(); assert.equal(s.timers.size, 0);
  s.visible(true); s.scheduler.resume(); s.fire(); assert.equal(s.count(), 1);
});
test('pending navigation prevents overlapping server refreshes', () => {
  const s = setup(); s.busy(true); s.scheduler.notify(); s.fire();
  assert.equal(s.count(), 0); assert.equal([...s.timers.values()][0].delay, 5000);
  s.busy(false); s.fire(); assert.equal(s.count(), 1);
});
test('unmount cancels pending work and ignores further events', () => {
  const s = setup(); s.scheduler.notify(); s.scheduler.dispose();
  s.scheduler.notify(); s.scheduler.resume(); assert.equal(s.timers.size, 0); assert.equal(s.count(), 0);
});
test('account polling routes and unrelated log events do not refresh whole pages', () => {
  assert.equal(shouldRefreshRoute('/', 'portfolio.marked'), false);
  assert.equal(shouldRefreshRoute('/opportunity-queue', 'price_refresh.completed'), false);
  assert.equal(shouldRefreshRoute('/invest', 'system_log.entry'), false);
  assert.equal(shouldRefreshRoute('/administration', 'system_log.entry'), true);
  assert.equal(shouldRefreshRoute('/invest/portfolio', 'portfolio.marked'), true);
  assert.equal(shouldRefreshRoute('/invest', 'quote.updated'), false);
});
