const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const source = readFileSync(join(__dirname, "..", "src", "App.jsx"), "utf8");

test("state-changing requests carry the expected protection header", () => {
  assert.match(source, /X-CSRF-Token/i);
});

test("the client has a readable token source", () => {
  assert.match(source, /document\.cookie|getCookie|csrfToken/i);
});
