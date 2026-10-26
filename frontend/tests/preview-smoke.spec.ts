import { test, expect } from "@playwright/test";

test("published preview exposes only reviewed works and cached administration", async ({ page }) => {
  test.skip(process.env.MEDIANEST_PREVIEW_SMOKE !== "1", "Requires explicitly selected local preview");
  const origin = new URL(process.env.MEDIANEST_CONTAINER_URL!).origin;
  const unexpected: string[] = [];
  const errors: string[] = [];
  await page.route("**/*", route => {
    const request = route.request();
    const url = new URL(request.url());
    const allowedWrite = ["/api/login", "/api/logout"].includes(url.pathname);
    if (url.origin !== origin || (request.method() !== "GET" && !allowedWrite)) {
      unexpected.push("blocked external or mutating request");
      return route.abort();
    }
    return route.continue();
  });
  page.on("pageerror", error => errors.push(error.name));
  const statsResponse = await page.request.get("/api/stats");
  expect(statsResponse.status()).toBe(200);
  const stats = await statsResponse.json();
  expect(stats).toMatchObject({ live_enabled: false, review: 0 });
  expect(stats.works).toBeGreaterThan(0);
  await page.goto("/");
  await expect(page.locator(".index-summary strong").nth(0)).toHaveText(String(stats.works));
  await expect(page.locator(".index-summary strong").nth(1)).toHaveText(String(stats.variants));
  await expect(page.locator(".poster-placeholder").first()).toContainText("暂无公开海报");
  await page.locator(".work-card").first().click();
  await expect(page.getByRole("heading", { name: "来源与版本", exact: true })).toBeVisible();
  const demoCards = page.locator(".version-card").filter({ hasText: "演示资源" });
  expect(await demoCards.count()).toBeGreaterThan(0);
  await expect(demoCards.getByRole("link", { name: "打开原分享" })).toHaveCount(0);
  await page.goto("/admin");
  await page.getByLabel("用户名", { exact: true }).fill(process.env.MEDIANEST_ADMIN || "demo");
  await page.getByLabel("密码", { exact: true }).fill(process.env.MEDIANEST_PASSWORD || "demo-access-2026");
  await page.getByRole("button", { name: "安全登录" }).click();
  await expect(page.getByRole("heading", { name: "管理控制台", exact: true })).toBeVisible();
  const pendingResponse = await page.request.get("/api/admin/review");
  expect(pendingResponse.status()).toBe(200);
  for (const work of (await pendingResponse.json()).items) {
    expect((await page.request.get(`/api/works/${work.id}`)).status()).toBe(404);
  }
  await page.getByRole("button", { name: "查看目录树" }).first().click();
  await expect(page.locator(".source-tree").first()).toBeVisible();
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
  expect(unexpected).toEqual([]);
  expect(errors).toEqual([]);
});
