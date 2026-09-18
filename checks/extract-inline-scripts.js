// Split inline scripts of an HTML file: classic scripts -> one shared-scope file,
// each module script -> its own file. Also collect globals provided by <script src>.
const fs=require('fs'), path=require('path');
const file=process.argv[2], outDir=process.argv[3];
const src=fs.readFileSync(file,'utf8');
const CDN_GLOBALS={
 leaflet:['L'], three:['THREE'], 'chart.js':['Chart'], chartjs:['Chart'], d3:['d3'],
 react:['React'], 'react-dom':['ReactDOM'], vue:['Vue'], lodash:['_'], jquery:['$','jQuery'],
 moment:['moment'], dayjs:['dayjs'], marked:['marked'], papaparse:['Papa'], xlsx:['XLSX'],
 html2canvas:['html2canvas'], jspdf:['jsPDF','jspdf'], alpine:['Alpine'], gsap:['gsap'],
 'canvas-confetti':['confetti'], lucide:['lucide'], feather:['feather'], sortable:['Sortable'],
 flatpickr:['flatpickr'], quill:['Quill'], codemirror:['CodeMirror'], 'anime':['anime'],
 p5:['p5'], tone:['Tone'], 'mapbox-gl':['mapboxgl'], 'socket.io':['io'], firebase:['firebase'],
 'supabase':['supabase'], tailwind:['tailwind'], babel:['Babel'], katex:['katex'],
 mathjax:['MathJax'], plotly:['Plotly'], echarts:['echarts'], 'apexcharts':['ApexCharts'],
 'qrcode':['QRCode','qrcode'], 'howler':['Howl','Howler'], 'axios':['axios'],
 'dompurify':['DOMPurify'], 'showdown':['showdown'], 'highlight':['hljs'], 'prism':['Prism'],
 'fullcalendar':['FullCalendar'], 'toastify':['Toastify'], 'swiper':['Swiper'],
 'matter':['Matter'], 'cannon':['CANNON'], 'pixi':['PIXI'], 'phaser':['Phaser'],
 'lottie':['lottie','bodymovin'], 'tesseract':['Tesseract'], 'pdf':['pdfjsLib','pdfMake'],
};
const extraGlobals=new Set();
// any <script src="..."> may define globals; guess from the URL
const srcRe=/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;
let sm;
while((sm=srcRe.exec(src))!==null){
  const url=sm[1].toLowerCase();
  for(const [k,v] of Object.entries(CDN_GLOBALS)) if(url.includes(k)) v.forEach(g=>extraGlobals.add(g));
}
const re=/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
let m; const classic=[]; const cmap=[]; const modules=[];
while((m=re.exec(src))!==null){
  const attrs=m[1]||'', body=m[2];
  if(/\bsrc\s*=/i.test(attrs)) continue;
  const tm=attrs.match(/type\s*=\s*["']?([^"'\s>]+)/i);
  const type=tm?tm[1].toLowerCase():'text/javascript';
  if(!['text/javascript','application/javascript','module',''].includes(type)) continue;
  if(!body.trim()) continue;
  const before=src.slice(0,m.index+m[0].indexOf('>')+1);
  const startLine=before.split('\n').length;
  const lines=body.split('\n');
  if(type==='module'){
    modules.push({body,startLine,map:lines.map((_,i)=>startLine+i)});
  } else {
    for(let i=0;i<lines.length;i++){classic.push(lines[i]);cmap.push(startLine+i);}
  }
}
fs.mkdirSync(outDir,{recursive:true});
const out={src:file,globals:[...extraGlobals],units:[]};
if(classic.length){
  fs.writeFileSync(path.join(outDir,'classic.js'),classic.join('\n'));
  out.units.push({file:'classic.js',map:cmap});
}
modules.forEach((mo,i)=>{
  fs.writeFileSync(path.join(outDir,`mod${i}.mjs`),mo.body);
  out.units.push({file:`mod${i}.mjs`,map:mo.map});
});
fs.writeFileSync(path.join(outDir,'meta.json'),JSON.stringify(out));
