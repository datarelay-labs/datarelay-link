// Offline, non-browser SSR checks for the real Link PF-5B Administration projection.
// These checks never substitute for Chromium/mobile User E2E or Core authorization.
import assert from "node:assert/strict";
import {after, before, test} from "node:test";
import {mkdtempSync, rmSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {
  AdministrationHub,
  effectiveAdministrationAvailability,
  validateAdministrationHub,
} from "@datarelay-labs/foundation";

const webRoot = dirname(dirname(fileURLToPath(import.meta.url)));
let scratch;
let createLinkFoundationAdministrationTasks;
before(async () => {
  // Transpile the actual product projection without a browser or new packages.
  // Emit below ignored node_modules so the pinned Foundation package resolves.
  scratch = mkdtempSync(join(webRoot, "node_modules", ".pf5b-admin-"));
  const outfile = join(scratch, "projection.mjs");
  await build({
    entryPoints: [join(webRoot, "src", "foundation-administration.ts")],
    outfile, bundle: true, platform: "node", format: "esm",
    external: ["@datarelay-labs/foundation"], logLevel: "silent",
  });
  ({createLinkFoundationAdministrationTasks} = await import(
    pathToFileURL(outfile).href
  ));
});
after(() => {
  if (scratch) rmSync(scratch, {recursive: true, force: true});
});

const canonicalTaskIds = [
  "core.https", "core.users", "core.password",
  "core.timezone", "core.network", "core.retention",
  "core.backup-import", "core.audit", "core.health",
];
const groupIds = [
  "access-security", "platform-network",
  "lifecycle-recovery", "operations-audit",
];
function projection(role) {
  const tasks = createLinkFoundationAdministrationTasks(role);
  validateAdministrationHub({productId: "link", tasks});
  assert.deepEqual(tasks.map(task => task.id), canonicalTaskIds);
  return tasks;
}
function markup(role) {
  return renderToStaticMarkup(React.createElement(AdministrationHub, {
    productId: "link", tasks: projection(role), showUnavailable: true,
    onOpen: () => {},
  }));
}

test("Admin gets one actionable Web user-management task", () => {
  const users = projection("Admin").find(t => t.id === "core.users");
  assert.equal(users.availability, "supported");
  assert.equal(users.access, "manage");
  assert.deepEqual(users.target, {kind: "action", actionId: "link.users"});
  assert.equal(effectiveAdministrationAvailability(users), "supported");
  const html = markup("Admin");
  assert.match(html, /aria-label="Manage User Management"/);
  assert.equal((html.match(/aria-label="Manage /g) || []).length, 1);
});

for (const role of ["Operator", "Read Only"]) {
  test(role + " has no Web user-management card or privileged action", () => {
    const users = projection(role).find(t => t.id === "core.users");
    assert.equal(users.availability, "supported"); // Link product truth
    assert.equal(users.access, "none"); // Actor permission truth
    assert.equal(users.target, undefined);
    assert.equal(effectiveAdministrationAvailability(users), "unavailable");
    const html = markup(role);
    assert.doesNotMatch(html, /User Management/);
    assert.equal((html.match(/aria-label="Manage /g) || []).length, 0);
  });
}

for (const role of ["Admin", "Operator", "Read Only"]) {
  test(role + " renders four canonical groups and only truthful actions", () => {
    const tasks = projection(role);
    const html = markup(role);
    assert.equal((html.match(/data-group-id="/g) || []).length, 4);
    for (const id of groupIds)
      assert.ok(html.includes('data-group-id="' + id + '"'), id);
    for (const label of ["HTTPS", "Audit", "System Health"])
      assert.ok(html.includes('aria-label="View ' + label + '"'), label);
    assert.equal((html.match(/aria-label="View /g) || []).length, 3);
    assert.match(html, /MCP TLS certificate status only/);
    assert.match(html, /Shared Web HTTPS listener and redirect configuration is not available/);
    for (const id of [
      "core.password", "core.timezone", "core.network",
      "core.retention", "core.backup-import",
    ]) {
      const task = tasks.find(t => t.id === id);
      assert.equal(task.availability, "unavailable", id);
      assert.equal(task.target, undefined, id);
    }
    assert.equal(tasks.filter(t => t.availability === "read_only").length, 3);
  });
}
