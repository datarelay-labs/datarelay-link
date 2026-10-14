import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync,statSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const dist=join(root,'dist');
const read=name=>readFileSync(join(dist,name),'utf8');

test('UXR-5.3 every runtime visual asset is local, present and non-empty',()=>{
 const index=read('index.html'),main=readFileSync(join(root,'src','main.tsx'),'utf8');
 const required=['index.html','app.js','styles.css','foundation.css','favicon.svg','logo/datarelay-logo.svg'];
 for(const name of required){
   const stat=statSync(join(dist,name));
   assert.equal(stat.isFile(),true,name);
   assert.ok(stat.size>100,name+' must be a real bundled asset');
 }
 for(const path of ['/favicon.svg','/styles.css','/foundation.css','/app.js'])
   assert.ok(index.includes(path),path+' must be same-origin');
 assert.ok(main.includes('src="/logo/datarelay-logo.svg"'),'brand logo must be same-origin');
 assert.doesNotMatch(index,/(?:src|href)=["']https?:\/\//i);
});

test('UXR-5.3 CSS and SVG assets do not load runtime CDN/font/image dependencies',()=>{
 const css=read('styles.css')+'\n'+read('foundation.css');
 const svg=read('favicon.svg')+'\n'+read('logo/datarelay-logo.svg');
 assert.doesNotMatch(css,/@import\s+/i);
 assert.doesNotMatch(css,/url\(\s*["']?https?:\/\//i);
 assert.doesNotMatch(css,/@font-face[\s\S]*?src\s*:\s*url\(/i);
 assert.doesNotMatch(svg,/(?:href|src)=["']https?:\/\//i);
 assert.match(svg,/viewBox=/);
});

test('UXR-5.3 product CSP remains self-only for executable/style/font/image assets',()=>{
 const source=readFileSync(join(dirname(root),'lib','drlink_web_service.py'),'utf8');
 assert.match(source,/default-src 'self'/);
 assert.match(source,/script-src 'self'/);
 assert.match(source,/style-src 'self'/);
 assert.match(source,/img-src 'self' data:/);
 assert.match(source,/font-src 'self'/);
 assert.match(source,/mimetypes\.guess_type/);
});
