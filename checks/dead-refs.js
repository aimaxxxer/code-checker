// Find <script src>, <link href>, <img src> pointing at local files that don't exist.
const fs=require('fs'), path=require('path');
const file=process.argv[2];
const dir=path.dirname(file);
const src=fs.readFileSync(file,'utf8');
const re=/<(script|link|img|source|iframe|audio|video)\b[^>]*?\b(src|href)\s*=\s*["']([^"']+)["']/gi;
let m;
while((m=re.exec(src))!==null){
  const url=m[3].trim();
  if(/^(https?:|data:|mailto:|tel:|#|\/\/|javascript:|blob:)/i.test(url)) continue;
  if(url.startsWith('/')) continue;             // server-root, can't resolve offline
  const clean=url.split('?')[0].split('#')[0];
  if(!clean) continue;
  const target=path.resolve(dir, clean);
  if(!fs.existsSync(target)){
    const line=src.slice(0,m.index).split('\n').length;
    console.log(`${file}:${line}: MISSING ${m[1]} ${m[2]}="${url}"`);
  }
}
