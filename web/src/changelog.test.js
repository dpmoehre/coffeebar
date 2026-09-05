import assert from "node:assert/strict";
import test from "node:test";

import { CHANGELOG, groupByDate } from "./changelog.js";

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

test("同一天的条目收进一组", () => {
  const days = groupByDate(CHANGELOG);
  assert.ok(days.length >= 1);
  assert.ok(days.length < CHANGELOG.length);
  const dates = days.map((d) => d.date);
  assert.equal(new Set(dates).size, dates.length);
  const sixth = days.find((d) => d.date === "2026-09-06");
  assert.ok(sixth && sixth.items.length >= 2);
  assert.ok(sixth.items.every((item) => item.date === "2026-09-06"));
});
