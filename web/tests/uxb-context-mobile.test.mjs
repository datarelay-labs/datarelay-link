// Source-level responsive contract only, not 320px/375px real browser acceptance.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const css=readFileSync(join(root,'dist','styles.css'),'utf8');
const contextRule=css.match(/^\.dr-uxb-context\{([^}]*)\}/m)?.[1]||'';

test('bounded Audit and Access context can wrap 160-character Core resource IDs on narrow screens',()=>{
  assert.match(contextRule,/\bmin-width\s*:\s*0\b/);
  assert.match(contextRule,/\boverflow-wrap\s*:\s*anywhere\b/);
});
test('context stays a reusable DRLink-owned style, with existing narrow workspace support',()=>{
  assert.match(css,/\.dr-uxb-context strong\{font-size:/);
  assert.match(css,/@media\(max-width:560px\)\{[^\n]*\.dr-workspace\{padding:12px\}/);
});
