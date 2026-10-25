import { test, expect } from "@playwright/test";

test("isolated demo container serves catalog and protected administration", async ({ page }, testInfo) => {
  test.skip(!process.env.MEDIANEST_CONTAINER_URL, "Only run against an explicitly selected disposable demo container");
  const origin = new URL(process.env.MEDIANEST_CONTAINER_URL!).origin;
  const blocked: string[] = [];
  const errors: string[] = [];
  const scans: string[] = [];
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) {
      blocked.push(url.hostname);
      return route.abort();
    }
    return route.continue();
  });
  page.on("pageerror", error => errors.push(error.name));
  page.on("request", request => {
    if (request.method() === "POST" && /\/sources\/.*\/scan$/.test(new URL(request.url()).pathname)) {
      scans.push("unexpected scan");
    }
  });
  const stats = await page.request.get("/api/stats");
  expect(stats.status()).toBe(200);
  expect(await stats.json()).toMatchObject({ mock: true, live_enabled: false, review: 0 });
  await page.goto("/");
  await expect(page.locator(".work-card").first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("catalog.png"), fullPage: true });
  await page.locator(".work-card").first().click();
  await expect(page.getByRole("heading", { name: "来源与版本", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "复制完整路径" }).first()).toBeVisible();
  await page.goto("/admin");
  await page.getByLabel("用户名", { exact: true }).fill("demo");
  await page.getByLabel("密码", { exact: true }).fill("demo-access-2026");
  await page.getByRole("button", { name: "安全登录" }).click();
  await expect(page.getByRole("heading", { name: "管理控制台", exact: true })).toBeVisible();
  const sourcesResponse = await page.request.get("/api/admin/sources");
  expect(sourcesResponse.status()).toBe(200);
  const sources = (await sourcesResponse.json()).items;
  expect(sources).toHaveLength(1);
  expect(sources[0].adapter).toBe("mock");
  await page.getByRole("button", { name: "查看目录树" }).first().click();
  await expect(page.locator(".source-tree").first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("sources.png"), fullPage: true });
  const review = await page.request.get("/api/admin/review");
  expect(review.status()).toBe(200);
  const pending = (await review.json()).items;
  expect(pending.length).toBeGreaterThan(0);
  for (const work of pending) {
    expect((await page.request.get(`/api/works/${work.id}`)).status()).toBe(404);
  }
  for (const section of ["sources", "jobs", "review", "health", "suggestions", "admins", "audits", "import"]) {
    await page.goto(`/admin/${section}`);
    await expect(page.getByRole("heading", { name: "管理控制台", exact: true })).toBeVisible();
    await expect(page.locator(".loading-line")).toHaveCount(0);
    await expect(page.locator(".error-banner")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "登录管理控制台", exact: true })).toBeVisible();
  expect((await page.request.get("/api/me")).status()).toBe(401);
  expect(blocked).toEqual([]);
  expect(errors).toEqual([]);
  expect(scans).toEqual([]);
});
