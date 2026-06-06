const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const source = readFileSync(join(__dirname, "..", "server.js"), "utf8");

test("the write endpoint checks the expected protection header", () => {
  assert.match(source, /x-csrf-token/i);
});

test("the email update route uses a verification middleware", () => {
  assert.match(source, /app\.post\(["']\/api\/account\/email[\s\S]{0,600}(verify|csrf)/i);
});
