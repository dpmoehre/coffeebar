import assert from "node:assert/strict";
import test from "node:test";

import { CHANGELOG } from "./changelog.js";

test("更新记录倒序、每条有日期标题和白话", () => {
  assert.ok(CHANGELOG.length >= 1);
  const dates = CHANGELOG.map((e) => e.date);
  const sorted = [...dates].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  assert.deepEqual(dates, sorted);
  for (const e of CHANGELOG) {
    assert.ok(e.date && e.title && e.notes?.length);
    assert.match(e.date, /^\d{4}-\d{2}-\d{2}$/);
  }
});
