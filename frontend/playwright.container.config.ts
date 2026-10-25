import { defineConfig, devices } from "@playwright/test";

const address = process.env.MEDIANEST_CONTAINER_URL;
if (!address) throw new Error("Set MEDIANEST_CONTAINER_URL to the isolated demo container's loopback URL");
const target = new URL(address);
if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" || !target.port ||
    target.username || target.password || target.pathname !== "/" || target.search || target.hash) {
  throw new Error("Container verification accepts only http://127.0.0.1:<port>/ without credentials");
}

export default defineConfig({
  testDir: "./tests",
  testMatch: "container-smoke.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: `../data/container-smoke-${Date.now()}`,
  use: {
    baseURL: target.origin,
    trace: "off", // Do not persist even the disposable demo session's tokens.
    launchOptions: { channel: process.env.PLAYWRIGHT_CHANNEL || "chrome" },
  },
  projects: [
    { name: "container-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "container-mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
  ],
});
