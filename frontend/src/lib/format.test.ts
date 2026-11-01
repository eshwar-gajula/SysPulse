import assert from "node:assert/strict";
import test from "node:test";
import { formatBytes, formatPercent, formatRate } from "./format.ts";

test("formats binary units without mutating input", () => {
  const bytes = 1024 ** 2;
  assert.equal(formatBytes(bytes), "1.0 MiB");
  assert.equal(bytes, 1024 ** 2);
});

test("handles empty, invalid, and rate values explicitly", () => {
  assert.equal(formatBytes(null), "—");
  assert.equal(formatBytes(Number.NaN), "—");
  assert.equal(formatRate(null), "—");
  assert.equal(formatPercent(87.26), "87.3%");
});
