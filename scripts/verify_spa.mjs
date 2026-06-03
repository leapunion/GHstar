#!/usr/bin/env node
// Behavioral verifier for the GHstar single-page app.
// Zero npm deps: built-in static server + Chrome via the DevTools Protocol
// (Node >= 22 globals: fetch, WebSocket). Uses any installed Chrome/Chromium
// (macOS dev box or GitHub-hosted runner) — no Playwright download required.
//
// Usage:
//   node scripts/verify_spa.mjs                 # self-serves ./public
//   node scripts/verify_spa.mjs --serve public --shot /tmp/spa.png
//   node scripts/verify_spa.mjs --url http://127.0.0.1:8000/   # external server
//
// Exit 0 = all assertions pass, 1 = a behavioral assertion failed,
// 3 = could not get a browser/server handle (environment problem).

import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFile, mkdtemp, readFile as rf, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, extname, normalize, resolve } from 'node:path';

const args = process.argv.slice(2);
const opt = (name, def) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : def; };
const ROOT = resolve(new URL('..', import.meta.url).pathname);
const serveDir = opt('--url') ? null : resolve(ROOT, opt('--serve', 'public'));
const shotPath = opt('--shot', join(tmpdir(), 'ghstar-spa.png'));

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };

function startStaticServer(dir) {
  return new Promise((res) => {
    const srv = createServer(async (req, reply) => {
      try {
        let p = decodeURIComponent(req.url.split('?')[0]);
        if (p.endsWith('/')) p += 'index.html';
        const full = join(dir, normalize(p));
        if (!full.startsWith(dir)) { reply.writeHead(403).end(); return; }
        const body = await readFile(full);
        reply.writeHead(200, { 'content-type': MIME[extname(full)] || 'application/octet-stream' });
        reply.end(body);
      } catch { reply.writeHead(404).end('not found'); }
    });
    srv.listen(0, '127.0.0.1', () => res({ srv, port: srv.address().port }));
  });
}

function findChrome() {
  if (process.env.CHROME && existsSync(process.env.CHROME)) return process.env.CHROME;
  const candidates = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome-stable', '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser', '/usr/bin/chromium',
  ];
  return candidates.find(existsSync) || 'google-chrome';
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launchChrome() {
  const profile = await mkdtemp(join(tmpdir(), 'ghstar-chrome-'));
  const bin = findChrome();
  const proc = spawn(bin, ['--headless=new', '--disable-gpu', '--no-first-run',
    '--no-default-browser-check', '--no-sandbox', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, '--window-size=1400,2200', 'about:blank'],
    { stdio: 'ignore' });
  // Chrome writes the chosen port to <profile>/DevToolsActivePort (line 1).
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 50; i++) {
    if (existsSync(portFile)) {
      const port = (await rf(portFile, 'utf8')).split('\n')[0].trim();
      if (port) return { proc, port: Number(port), bin };
    }
    await sleep(100);
  }
  proc.kill('SIGKILL');
  throw new Error(`chrome did not expose a debug port (bin=${bin})`);
}

async function main() {
  let server = null, base = opt('--url');
  if (!base) { server = await startStaticServer(serveDir); base = `http://127.0.0.1:${server.port}/`; }

  let chrome;
  try { chrome = await launchChrome(); }
  catch (e) { console.error('HANDLE_FAIL:', e.message); process.exit(3); }

  // Discover the page target and open a CDP socket.
  let target;
  for (let i = 0; i < 40; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${chrome.port}/json`)).json()).find(t => t.type === 'page'); } catch {}
    if (target) break; await sleep(150);
  }
  if (!target) { console.error('HANDLE_FAIL: no page target'); chrome.proc.kill('SIGKILL'); process.exit(3); }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 1; const pending = new Map(); const exceptions = []; const consoleErrors = [];
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const { ok, no } = pending.get(m.id); pending.delete(m.id); m.error ? no(new Error(JSON.stringify(m.error))) : ok(m.result); }
    else if (m.method === 'Runtime.exceptionThrown') exceptions.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value ?? a.description ?? '').join(' '));
  };
  const send = (method, params = {}) => new Promise((ok, no) => { const i = id++; pending.set(i, { ok, no }); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJS = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error('eval: ' + r.exceptionDetails.text); return r.result.value; };
  const count = () => evalJS(`document.querySelectorAll('.repo-card').length`);
  const drive = async (expr) => { await evalJS(expr); await sleep(400); return count(); };

  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');
  await send('Page.navigate', { url: base });

  // Wait for first render.
  let initial = 0;
  for (let i = 0; i < 50; i++) { initial = await count(); if (initial > 0) break; await sleep(200); }

  const checks = [];
  const assert = (name, pass, detail) => { checks.push({ name, pass: !!pass, detail }); };

  assert('cards render', initial > 0, `${initial} cards`);

  // Sparklines live in the corpus (repo-centric) view, which carries per-repo
  // history. Measure here, before any filter switches to the day-centric
  // snapshot view (which omits history by contract).
  const sparks = await evalJS(`document.querySelectorAll('.spa-spark, .score-chart svg, svg').length`);
  assert('sparklines render', sparks > 0, `${sparks} svg in corpus view`);

  const cat = await drive(`(()=>{const s=document.querySelector('#f-category');const o=[...s.options].find(x=>x.value);if(!o)return;[...s.options].forEach(x=>x.selected=false);o.selected=true;s.dispatchEvent(new Event('change',{bubbles:true}));return o.value;})()`);
  assert('category filter narrows', cat > 0 && cat <= initial, `category -> ${cat} (<= ${initial})`);

  await evalJS(`document.querySelector('#btn-reset').click()`); await sleep(350);
  const afterReset = await count();
  assert('reset restores full list', afterReset === initial, `reset -> ${afterReset}`);

  const kw = await drive(`(()=>{const k=document.querySelector('#f-keyword');k.value='agent';k.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  assert('keyword filter applies', kw > 0 && kw <= initial, `keyword 'agent' -> ${kw}`);
  await evalJS(`document.querySelector('#btn-reset').click()`); await sleep(350);

  await evalJS(`(()=>{const d=document.querySelector('#f-date');const o=[...d.options].find(x=>x.value&&x.value!=='all');if(o){d.value=o.value;d.dispatchEvent(new Event('change',{bubbles:true}));}})()`);
  await sleep(700);
  const dateCount = await count();
  const dateUsed = await evalJS(`document.querySelector('#f-date').value`);
  assert('single-date snapshot view loads', dateCount > 0, `date ${dateUsed} -> ${dateCount} cards`);

  assert('no uncaught exceptions', exceptions.length === 0, exceptions.slice(0, 3).join(' | ') || 'none');

  await evalJS(`document.querySelector('#btn-reset').click()`); await sleep(400);
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  await writeFile(shotPath, Buffer.from(shot.data, 'base64'));

  ws.close(); chrome.proc.kill('SIGKILL'); if (server) server.srv.close();

  const failed = checks.filter(c => !c.pass);
  const report = { verdict: failed.length ? 'FAIL' : 'PASS', base, chrome: chrome.bin, initial_cards: initial,
    screenshot: shotPath, console_errors: consoleErrors, checks };
  console.log(JSON.stringify(report, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => { console.error('ERROR:', e.message); process.exit(3); });
