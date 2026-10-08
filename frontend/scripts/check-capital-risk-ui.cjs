// Exercise the real component in an isolated Chrome tab with a mocked API.
// Requires Chrome's local debugging port (default 9333). Never accesses an account.
(async () => {
  const fs = await import('node:fs');
  const os = await import('node:os');
  const path = await import('node:path');
  const {default: assert} = await import('node:assert/strict');
  const {default: ts} = await import('typescript');
  const {default: bundler} = await import('next/dist/compiled/webpack/webpack.js');
  const {webpack} = bundler;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'capital-risk-ui-'));
  const source = fs.readFileSync('src/components/settings/CapitalRiskSettings.tsx', 'utf8');
  fs.writeFileSync(path.join(dir, 'component.js'), ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020,
  }}).outputText);
  fs.writeFileSync(path.join(dir, 'api.js'), `
    let profile = 'medium';
    window.requests = [];
    const options = Object.fromEntries(['low','medium','high'].map((name, i) => [name, {
      max_position_pct: [3,5,5][i], max_etf_position_pct:[5,10,20][i], max_positions:[3,5,8][i],
      cash_reserve_pct:[60,20,20][i], risk_per_trade_pct:[.25,.5,1][i],
      max_aggregate_risk_pct:[.75,1.5,3][i], max_daily_loss_pct:[1,2,3][i],
      max_drawdown_pct:[3,5,8][i], max_sector_pct:[10,20,25][i], max_correlated_exposure_pct:[6,15,20][i]
    }]));
    export async function getCapitalRiskSettings() {
      const result = {profile, options, notice:'Account limits apply.'};
      if(window.slowReload) await new Promise(resolve => setTimeout(resolve, 300));
      return result;
    }
    export async function saveCapitalRiskSettings(selected, expected) {
      window.requests.push({selected, expected});
      await new Promise(resolve => setTimeout(resolve, 100));
      if (window.failSave) throw new Error('Simulated save failure');
      if (expected !== profile) throw new Error('Stale selection');
      profile = selected;
      return getCapitalRiskSettings();
    }
  `);
  fs.writeFileSync(path.join(dir, 'toast.js'), 'export const toast = {success(message) { window.lastToast = message; }};');
  fs.writeFileSync(path.join(dir, 'entry.js'), `import React from 'react'; import {createRoot} from 'react-dom/client'; import {CapitalRiskSettings} from './component'; createRoot(document.getElementById('root')).render(React.createElement(CapitalRiskSettings));`);
  await new Promise((resolve, reject) => webpack({ mode:'development', devtool:false, context:dir,
    entry:'./entry.js', output:{path:dir, filename:'bundle.js'},
    resolve:{modules:[path.resolve('node_modules')], alias:{'@/lib/api':path.join(dir,'api.js'), '@/components/ui/ToastProvider':path.join(dir,'toast.js')}}
  }, (error, stats) => error || stats.hasErrors() ? reject(error || new Error(stats.toString())) : resolve()));
  fs.writeFileSync(path.join(dir, 'index.html'), '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="root"></main><script src="bundle.js"></script></body></html>');
  const base = `http://127.0.0.1:${process.env.CHROME_DEBUG_PORT || 9333}`;
  const tab = await (await fetch(`${base}/json/new?about:blank`, {method:'PUT'})).json();
  const socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}));
  let serial=0; const pending = new Map();
  socket.addEventListener('message', event => { const message=JSON.parse(event.data); if (message.id) {
    const item = pending.get(message.id); pending.delete(message.id);
    if (message.error) item.reject(new Error(JSON.stringify(message.error)));
    else item.resolve(message.result);
  }});
  const send = (method, params={}) => new Promise((resolve,reject) => { const id=++serial; pending.set(id,{resolve,reject}); socket.send(JSON.stringify({id,method,params})); });
  const evaluate = async expression => { const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true}); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  const waitFor = async expression => { for(let i=0;i<100;i++) { if(await evaluate(expression)) return; await new Promise(resolve=>setTimeout(resolve,50)); } throw new Error(`Timed out: ${expression}`); };
  try {
    await send('Page.enable');
    await send('Page.navigate',{url:`file://${path.join(dir,'index.html')}`});
    await waitFor('document.querySelectorAll("input[type=radio]").length === 3');
    assert.equal(await evaluate('document.querySelector("input:checked").value'), 'medium');
    assert.equal(await evaluate('document.querySelector("section > button").disabled'), true);
    await evaluate('document.querySelector("input[value=high]").click()');
    await waitFor('document.querySelector("input:checked").value === "high"');
    assert.equal(await evaluate('window.requests.length'), 0);
    await evaluate('window.failSave=true; document.querySelector("section > button").click()');
    await waitFor('document.querySelector("[role=alert]")?.textContent.includes("Simulated save failure")');
    assert.equal(await evaluate('document.body.textContent.includes("Saved: medium")'), true);
    await evaluate('window.slowReload=true; document.querySelector("[role=alert] button").click()');
    assert.equal(await evaluate('document.querySelector("section > button").disabled && document.querySelector("fieldset").disabled'), true);
    await waitFor('!document.querySelector("fieldset").disabled');
    await evaluate('window.slowReload=false; document.querySelector("input[value=high]").click()');
    await evaluate('window.failSave=false; document.querySelector("section > button").click()');
    await waitFor('document.body.textContent.includes("Saved: high")');
    assert.deepEqual(await evaluate('window.requests[1]'), {selected:'high',expected:'medium'});
    await evaluate('document.querySelector("input[value=low]").click()');
    await waitFor('document.querySelector("input:checked").value === "low"');
    await evaluate('document.querySelector("section > button").click()');
    await waitFor('document.body.textContent.includes("Saved: low")');
    assert.deepEqual(await evaluate('window.requests[2]'), {selected:'low',expected:'high'});
    assert.equal(await evaluate('document.querySelector("section > button").disabled'), true);
    console.log('Risk settings browser checks passed: load, 3 choices, explicit save, failed save preserves profile, retry, saved profile updates, subsequent save uses current revision. API mocked; no account changes.');
  } finally {
    socket.close();
    await fetch(`${base}/json/close/${tab.id}`);
    fs.rmSync(dir,{recursive:true,force:true});
  }
})().catch(error => { console.error(error); process.exitCode=1; });
