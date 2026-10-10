import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {once} from "node:events";
import path from "node:path";
import {fileURLToPath} from "node:url";
import test from "node:test";

import {apiBaseUrl, DEFAULT_BASE_URL, request, taskRequest} from "../scripts/lululab_cli.mjs";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const client = path.join(root, "scripts", "lululab_cli.mjs");

async function run(args, key = "fixture-key") {
  const child = spawn(process.execPath, [client, ...args], {stdio: ["pipe", "pipe", "pipe"]});
  child.stdin.end(key + "\n");
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8").on("data", (value) => { stdout += value; });
  child.stderr.setEncoding("utf8").on("data", (value) => { stderr += value; });
  const [code] = await once(child, "close");
  return {code, stdout, stderr};
}

test("uses the documented production origin and rejects insecure remote origins", () => {
  assert.equal(DEFAULT_BASE_URL, "https://customer.lululab.ai");
  assert.equal(apiBaseUrl(DEFAULT_BASE_URL), DEFAULT_BASE_URL);
  assert.throws(() => apiBaseUrl("http://example.com"), /LULULAB_BASE_URL_MUST_USE_HTTPS/);
});

test("builds documented submit request with a raw Authorization key", () => {
  const spec = taskRequest({action: "submit", base: DEFAULT_BASE_URL, apiKey: "fixture-key",
    workflowId: "VideoTranslatePolicyV1", input: {action: "cleanup_policy"}});
  assert.equal(spec.url, "https://customer.lululab.ai/tasks");
  assert.equal(spec.options.method, "POST");
  assert.equal(spec.options.headers.Authorization, "fixture-key");
  assert.equal(spec.options.headers.Authorization.startsWith("Bearer "), false);
  assert.deepEqual(JSON.parse(spec.options.body),
    {workflowId: "VideoTranslatePolicyV1", input: {action: "cleanup_policy"}});
});

test("builds documented fetch request and parses a task response", async () => {
  const spec = taskRequest({action: "fetch", base: DEFAULT_BASE_URL, apiKey: "fixture-key", id: "task/2"});
  assert.equal(spec.url, "https://customer.lululab.ai/tasks/task%2F2");
  assert.equal(spec.options.method, "GET");
  const result = await request(spec, async (url, options) => {
    assert.equal(url, spec.url);
    assert.equal(options.headers.Authorization, "fixture-key");
    return {ok: true, status: 200, text: async () => JSON.stringify({id: "task-2", status: "Succeeded"})};
  });
  assert.deepEqual(result, {ok: true, value: {id: "task-2", status: "Succeeded"}});
});

test("never accepts an API key argument", async () => {
  const result = await run(["task", "fetch", "--api-key", "fixture-key", "--id", "task-2"]);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /API_KEY_STDIN_REQUIRED|UNKNOWN_OPTION/);
  assert.equal(result.stdout, "");
});
