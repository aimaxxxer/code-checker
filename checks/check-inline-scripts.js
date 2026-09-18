// Syntax-check every inline <script> in an HTML file.
// Classic scripts are parsed in-process; module scripts go through
// `node --input-type=module --check`, which needs no experimental flag.
// Exits non-zero if anything failed to parse.
const fs = require('fs');
const vm = require('vm');
const { spawnSync } = require('child_process');

const file = process.argv[2];
if (!file) { console.error('usage: check-inline-scripts.js FILE.html'); process.exit(2); }
const src = fs.readFileSync(file, 'utf8');

const re = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
let m, idx = 0, problems = 0;
while ((m = re.exec(src)) !== null) {
  const attrs = m[1] || '', body = m[2];
  idx++;
  if (/\bsrc\s*=/i.test(attrs)) continue;                 // external file
  const tm = attrs.match(/type\s*=\s*["']?([^"'\s>]+)/i);
  const type = tm ? tm[1].toLowerCase() : 'text/javascript';
  // anything else is a template or JSON-LD, not script
  if (!['text/javascript', 'application/javascript', 'module', ''].includes(type)) continue;
  if (!body.trim()) continue;

  const startLine = src.slice(0, m.index + m[0].indexOf('>') + 1).split('\n').length;

  let err = null;
  if (type === 'module') {
    const r = spawnSync(process.execPath, ['--input-type=module', '--check'],
                        { input: body, encoding: 'utf8' });
    if (r.status !== 0) err = (r.stderr || '').split('\n').find(l => /Error/.test(l)) || 'parse error';
  } else {
    try { new vm.Script(body, { filename: file }); }
    catch (e) { err = e.message.split('\n')[0]; }
  }

  if (err) {
    problems++;
    console.log(`SYNTAX ${file} (script #${idx}, starts line ${startLine}): ${err}`);
  }
}
process.exit(problems ? 1 : 0);
