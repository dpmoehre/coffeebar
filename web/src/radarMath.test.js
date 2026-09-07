import assert from "node:assert/strict";
import test from "node:test";

import { pickScore } from "./radarMath.js";

const C = 110;
const R = 76;

test("正上方是干香 10", () => {
  assert.deepEqual(pickScore(C, C - R, C, R), { i: 0, score: 10 });
});

test("正右是风味 10", () => {
  assert.deepEqual(pickScore(C + R, C, C, R), { i: 1, score: 10 });
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
