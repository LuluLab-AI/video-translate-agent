#!/usr/bin/env node
import {pathToFileURL} from "node:url";

export const DEFAULT_BASE_URL = "https://customer.lululab.ai";
const MAX_KEY_CHARS = 4096;

function fail(code, details = {}) {
  process.stderr.write(JSON.stringify({error: code, ...details}) + "\n");
  return 1;
}

function option(args, name, {required = false} = {}) {
  const positions = args.flatMap((value, index) => value === name ? [index] : []);
  if (positions.length > 1) throw new Error(`DUPLICATE_OPTION:${name}`);
  if (!positions.length) {
    if (required) throw new Error(`MISSING_OPTION:${name}`);
    return undefined;
  }
  const value = args[positions[0] + 1];
  if (!value || value.startsWith("--")) throw new Error(`MISSING_OPTION_VALUE:${name}`);
  return value;
}

function validateArgs(args, allowed) {
  for (let index = 2; index < args.length; index += 1) {
    const value = args[index];
    if (!value.startsWith("--")) continue;
    if (value === "--api-key-stdin") continue;
    if (!allowed.has(value)) throw new Error(`UNKNOWN_OPTION:${value}`);
    index += 1;
  }
  if (!args.includes("--api-key-stdin")) throw new Error("API_KEY_STDIN_REQUIRED");
}

export function apiBaseUrl(value = DEFAULT_BASE_URL) {
  const url = new URL(value);
  const loopback = ["127.0.0.1", "::1", "localhost"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) {
    throw new Error("LULULAB_BASE_URL_MUST_USE_HTTPS");
  }
  url.pathname = url.pathname.replace(/\/+$/, "");
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

async function readApiKey(stream = process.stdin) {
  let input = "";
  for await (const chunk of stream) {
    input += chunk.toString("utf8");
    if (input.length > MAX_KEY_CHARS + 2) throw new Error("CREDENTIAL_INPUT_TOO_LARGE");
  }
  const lines = input.replace(/\r\n/g, "\n").split("\n");
  const key = lines.shift()?.trim() ?? "";
  if (!key) throw new Error("LULULAB_CREDENTIAL_REQUIRED");
  if (key.length > MAX_KEY_CHARS) throw new Error("CREDENTIAL_INPUT_TOO_LARGE");
  if (lines.some((line) => line.trim())) throw new Error("CREDENTIAL_INPUT_MULTILINE");
  return key;
}

export function taskRequest({action, base, apiKey, workflowId, input, id}) {
  const headers = {Accept: "application/json"};
  headers["Authorization"] = apiKey;
  if (action === "submit") {
    headers["Content-Type"] = "application/json";
    return {
      url: `${base}/tasks`,
      options: {method: "POST", headers, body: JSON.stringify({workflowId, input}), redirect: "error"},
    };
  }
  return {
    url: `${base}/tasks/${encodeURIComponent(id)}`,
    options: {method: "GET", headers, body: undefined, redirect: "error"},
  };
}

export async function request({url, options}, fetchImpl = fetch) {
  const response = await fetchImpl(url, options);
  const text = await response.text();
  let value;
  try {
    value = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`LULULAB_INVALID_JSON:${response.status}`);
  }
  if (!response.ok) {
    process.stderr.write(JSON.stringify({error: "LULULAB_HTTP_ERROR", status: response.status, body: value}) + "\n");
    return {ok: false};
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("LULULAB_INVALID_JSON_OBJECT");
  }
  return {ok: true, value};
}

export async function main(args = process.argv.slice(2)) {
  try {
    const [group, action] = args;
    if (group !== "task" || !["submit", "fetch"].includes(action)) {
      throw new Error("USAGE: task submit|fetch");
    }
    const allowed = new Set(action === "submit"
      ? ["--workflow-id", "--input", "--base-url"]
      : ["--id", "--base-url"]);
    validateArgs(args, allowed);
    const base = apiBaseUrl(option(args, "--base-url") || process.env.LULULAB_API_BASE_URL || DEFAULT_BASE_URL);
    const apiKey = await readApiKey();
    let result;
    if (action === "submit") {
      const workflowId = option(args, "--workflow-id", {required: true});
      const rawInput = option(args, "--input", {required: true});
      let input;
      try {
        input = JSON.parse(rawInput);
      } catch {
        throw new Error("INVALID_TASK_INPUT_JSON");
      }
      result = await request(taskRequest({action, base, apiKey, workflowId, input}));
    } else {
      const id = option(args, "--id", {required: true});
      result = await request(taskRequest({action, base, apiKey, id}));
    }
    if (!result.ok) return 1;
    process.stdout.write(JSON.stringify(result.value) + "\n");
    return 0;
  } catch (error) {
    return fail(String(error?.message || "LULULAB_CLIENT_FAILED"));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
