import assert from "node:assert/strict";
import test from "node:test";

import { unview, zoomAt } from "./view.js";

test("unview 是缩放平移的逆", () => {
  const [px, py] = unview(10 + 2 * 50, 20 + 2 * 80, { k: 2, x: 10, y: 20 });
  assert.equal(px, 50);
  assert.equal(py, 80);
});

test("zoomAt 后鼠标下的地图点不变", () => {
  const next = zoomAt({ k: 1, x: 0, y: 0 }, 100, 80, 2);
  const [px, py] = unview(100, 80, next);
  assert.equal(px, 100);
  assert.equal(py, 80);
});

test("缩小后再放大，鼠标下的点仍对得上", () => {
  const mid = zoomAt({ k: 1, x: 0, y: 0 }, 40, 60, 1 / 1.12);
  const back = zoomAt(mid, 40, 60, 1.12);
  const [px, py] = unview(40, 60, back);
  assert.ok(Math.abs(px - 40) < 1e-9);
  assert.ok(Math.abs(py - 60) < 1e-9);
});
