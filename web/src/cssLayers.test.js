import assert from "node:assert/strict";
import test from "node:test";

import { flattenCssLayers } from "./cssLayers.js";

test("拆开单层，内容顺序不变", () => {
  const out = flattenCssLayers("@layer utilities{.h-4{height:1rem}.w-4{width:1rem}}html{font-size:15px}");
  assert.equal(out, ".h-4{height:1rem}.w-4{width:1rem}html{font-size:15px}");
});

test("多层按原顺序摊开，主题变量还在", () => {
  const out = flattenCssLayers(
    "@layer theme{:root{--spacing:.25rem;--color-bg:#12100e}}@layer utilities{.h-4{height:calc(var(--spacing)*4)}}body{background:var(--color-bg)}",
  );
  assert.equal(
    out,
    ":root{--spacing:.25rem;--color-bg:#12100e}.h-4{height:calc(var(--spacing)*4)}body{background:var(--color-bg)}",
  );
});

test("层里的普通 @supports 嵌套括号不会截断", () => {
  const out = flattenCssLayers(
    "@layer properties{@supports (display:grid){*{--tw-shadow:0 0 #0000}}}.rise{opacity:1}",
  );
  assert.equal(out, "@supports (display:grid){*{--tw-shadow:0 0 #0000}}.rise{opacity:1}");
});

test("空的 @layer 顺序声明删掉", () => {
  const out = flattenCssLayers("@layer theme, utilities;:root{--a:1}");
  assert.equal(out, ":root{--a:1}");
});

test("字符串里的花括号不当闭合", () => {
  const out = flattenCssLayers('@layer base{dialog{background:url("data:x{y}")}}.ok{color:red}');
  assert.equal(out, 'dialog{background:url("data:x{y}")}.ok{color:red}');
});

test("开头的 relative-color @supports 会整段拿掉", () => {
  const out = flattenCssLayers(
    "@layer properties{@supports (((-webkit-hyphens:none)) and (not (color:rgb(from red r g b)))){*{--tw-shadow:0 0 #0000}}}:root{--color-bg:#12100e}",
  );
  assert.equal(out, ":root{--color-bg:#12100e}");
  assert.equal(out.includes("rgb(from"), false);
});
