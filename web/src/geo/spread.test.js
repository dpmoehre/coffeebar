import assert from "node:assert/strict";
import test from "node:test";

import { spreadLatLng, spreadScreen } from "./spread.js";

test("同一像素的两颗钉会左右分开", () => {
  const out = spreadScreen(
    [
      { bean_id: 1, place_id: 1, x: 10, y: 10 },
      { bean_id: 2, place_id: 2, x: 10, y: 10 },
    ],
    1,
    26
  );
  assert.equal(out.length, 2);
  const d = Math.hypot(out[0].sx - out[1].sx, out[0].sy - out[1].sy);
  assert.ok(d > 20);
});

test("离得远的钉仍停在真点", () => {
  const out = spreadScreen(
    [
      { bean_id: 1, place_id: 1, x: 0, y: 0 },
      { bean_id: 2, place_id: 2, x: 200, y: 0 },
    ],
    1,
    26
  );
  const a = out.find((p) => p.bean_id === 1);
  const b = out.find((p) => p.bean_id === 2);
  assert.equal(a.sx, 0);
  assert.equal(b.sx, 200);
});

test("缩小时不会把本来分得开的钉拉成一圈", () => {
  const out = spreadScreen(
    [
      { bean_id: 1, place_id: 1, x: 0, y: 0 },
      { bean_id: 2, place_id: 2, x: 30, y: 0 },
    ],
    0.7,
    26
  );
  const a = out.find((p) => p.bean_id === 1);
  const b = out.find((p) => p.bean_id === 2);
  assert.equal(a.sx, 0);
  assert.equal(b.sx, 30);
});

test("隔开十几像素的钉不并成一圈", () => {
  const out = spreadScreen(
    [
      { bean_id: 1, place_id: 1, x: 0, y: 0 },
      { bean_id: 2, place_id: 2, x: 15, y: 0 },
    ],
    1,
    26
  );
  assert.equal(out.find((p) => p.bean_id === 1).sx, 0);
  assert.equal(out.find((p) => p.bean_id === 2).sx, 15);
});

test("放大后几乎重叠的两颗会各自回到真点", () => {
  const pair = [
    { bean_id: 1, place_id: 1, x: 0, y: 0 },
    { bean_id: 2, place_id: 2, x: 6, y: 0 },
  ];
  const wide = spreadScreen(pair, 1, 26);
  assert.ok(wide.some((p) => Math.hypot(p.sx - p.x, p.sy - p.y) > 1));
  const close = spreadScreen(pair, 4, 26);
  const stayed = close.find((p) => p.bean_id === 1);
  assert.equal(stayed.sx, 0);
  assert.equal(stayed.sy, 0);
});

test("地球上同一经纬度的两颗钉会错开", () => {
  const out = spreadLatLng([
    { bean_id: 1, place_id: 1, lat: 6.16, lng: 38.2 },
    { bean_id: 2, place_id: 2, lat: 6.16, lng: 38.2 },
  ]);
  assert.ok(Math.hypot(out[0].plat - out[1].plat, out[0].plng - out[1].plng) > 0.2);
  assert.equal(out[0].lat, 6.16);
});
