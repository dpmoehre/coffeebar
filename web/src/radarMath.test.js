import assert from "node:assert/strict";
import test from "node:test";

import { fmtScore, hasDims, pickScore } from "./radarMath.js";

const C = 110;
const R = 76;

test("正上方是干香 10", () => {
  assert.deepEqual(pickScore(C, C - R, C, R), { i: 0, score: 10 });
});

test("正右是余韵 10（八维里风味在右上）", () => {
  assert.deepEqual(pickScore(C + R, C, C, R), { i: 2, score: 10 });
});

test("右上 45 度是风味 10", () => {
  const x = C + R * Math.SQRT1_2;
  const y = C - R * Math.SQRT1_2;
  assert.deepEqual(pickScore(x, y, C, R), { i: 1, score: 10 });
});

test("中心是 0", () => {
  assert.equal(pickScore(C, C, C, R).score, 0);
});

test("干香轴一半是 5", () => {
  assert.deepEqual(pickScore(C, C - R / 2, C, R), { i: 0, score: 5 });
});

test("超出外圈仍是 10", () => {
  assert.equal(pickScore(C, C - R * 2, C, R).score, 10);
});

test("均分有一位小数，整数不带点", () => {
  assert.equal(fmtScore(7), "7");
  assert.equal(fmtScore(7.3), "7.3");
  assert.equal(hasDims({ acidity: 7 }), true);
  assert.equal(hasDims({ acidity: null }), false);
});
