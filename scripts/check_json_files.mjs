import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import {
  MAX_PROJECT_BYTES, MAX_BUNDLE_BYTES, parseStrictJSON, readJSONFile, projectBlob,
} from "../mazeproof/web/files.js";

const valid = [
  "{}", "[]", "null", "true", "false", "-0", "1.25e-3",
  ' {"a":[1,2,{"b":"\\\"\\\\\\u0077"}],"c":false} ',
  '{"__proto__":{"polluted":true},"constructor":1}',
  '{"a":{"width":1},"b":{"width":2},"日本語":"迷路🙂"}',
];
for (const text of valid) assert.deepEqual(parseStrictJSON(text), JSON.parse(text));
assert.equal({}.polluted, undefined);
const malformed = [
  "", " ", "[", "{", '{"a":}', '{"a":1,}', '[1,]', "[01]", "1.",
  "true false", "undefined", "NaN", "Infinity", '"unclosed', '"bad\\x"',
  '"literal\nnewline"', '{"a" 1}', '{1:2}', "[1 2]", '"\\u0xyz"',
  '"control\u0001"', "{".repeat(101), "[".repeat(102) + "]".repeat(102),
];
for (const text of malformed) assert.throws(() => parseStrictJSON(text), Error);
for (const text of [
  '{"width":99,"width":2}',
  '{"width":99,"\\u0077idth":2}',
  '{"a":[{"row":0,"row":1}]}',
  '{"__proto__":{},"__proto__":null}',
  '{"🙂":1,"\\ud83d\\ude42":2}',
]) assert.throws(() => parseStrictJSON(text), /重複/);
for (const text of ["1e999", "-1e999", '{"x":1e999}'])
  assert.throws(() => parseStrictJSON(text), /数値/);

// Independent native parser comparison over varied legal nested values.
for (let i = 0; i < 300; i++) {
  const value = { index: i, cells: [{row: i % 250, col: (i * 7) % 250}],
    names: ["quote\"slash\\", "日本語🙂", "line\n\t"],
    open: i % 2 === 0, empty: null, number: (i - 150) / 7 };
  const text = JSON.stringify(value, null, i % 3);
  assert.deepEqual(parseStrictJSON(text), value);
}

const sizeMessage = "size rejected before reading";
await assert.rejects(readJSONFile({size: MAX_PROJECT_BYTES + 1,
  text() { throw new Error("must not read"); }}, MAX_PROJECT_BYTES, sizeMessage), /size rejected/);
const project = {name: "原画像.png", edits: [{row: 0, col: 1}]};
const blob = projectBlob(project);
assert.equal(blob.size, Buffer.byteLength(JSON.stringify(project)));
assert.deepEqual(await readJSONFile(blob, MAX_PROJECT_BYTES, sizeMessage), project);
assert.equal(MAX_PROJECT_BYTES, 128 * 1024 * 1024);
assert.equal(MAX_BUNDLE_BYTES, 128 * 1024 * 1024);

// The browser and Python share acceptance/rejection of reference structure JSON.
const fixture = readFileSync(new URL('../tests/fixtures/unique-2x2.json', import.meta.url), 'utf8');
for (const raw of [fixture, fixture.replace('"width": 2', '"width":99,"width":2'), fixture.replace('"width": 2', '"width":99,"\\u0077idth":2')]) {
  let accepted = true;
  try { parseStrictJSON(raw); } catch { accepted = false; }
  const py = spawnSync(process.env.PYTHON || "python", ["-c", "import sys;from mazeproof.core import validate_structure;print(validate_structure(sys.stdin.read())['overallStatus'])"], {input:raw, encoding:'utf8'});
  assert.equal(py.status, 0, py.stderr);
  assert.equal(accepted, py.stdout.trim() !== "INVALID_INPUT");
}
const constants = spawnSync(process.env.PYTHON || "python", ["-c", "from mazeproof.workspace import MAX_PROJECT_BYTES,MAX_PROJECT_REQUEST_BYTES;print(MAX_PROJECT_BYTES,MAX_PROJECT_REQUEST_BYTES)"], {encoding:'utf8'});
assert.equal(constants.status, 0, constants.stderr);
assert.deepEqual(constants.stdout.trim().split(" ").map(Number), [MAX_PROJECT_BYTES, MAX_PROJECT_BYTES + 1024]);
console.log("Strict JSON: duplicate/escaped/nested keys, invalid grammar, finite numbers, safe objects, 300 native-parser comparisons, file limits, Python parity: OK");
