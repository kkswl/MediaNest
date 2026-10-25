import { test, expect } from "@playwright/test";

test("local backend integration with synthetic sources only", async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.YINGJI_LOCAL_INTEGRATION !== "1",
    "需要先按 README 初始化本地模拟数据库并运行 8000 API；不连接真实115",
  );
  const remoteRequests: string[] = [];
  const pageErrors: string[] = [];
  page.on("request", (request) => {
    if (
      !request.url().startsWith("http://127.0.0.1:5173") &&
      !request.url().startsWith("data:")
    )
      remoteRequests.push(request.url());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".work-card").first()).toBeVisible();
  await expect(page.getByText("本地模拟资料", { exact: false })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `artifacts/catalog-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.locator(".work-card").first().click();
  await expect(
    page.getByRole("heading", { name: "来源与版本", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "复制完整路径" }).first(),
  ).toBeVisible();
  const proposedTitle = "模拟纠错验证" + Date.now() + testInfo.project.name;
  await page.getByRole("button", { name: "提交资料纠错" }).click();
  await page.getByLabel("正确片名", { exact: true }).fill(proposedTitle);
  await page.getByRole("button", { name: "提交审核", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("建议已提交");
  await page.screenshot({
    path: `artifacts/detail-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.goto("/admin");
  await page.getByLabel("用户名", { exact: true }).fill("demo");
  await page.getByLabel("密码", { exact: true }).fill("demo-access-2026");
  await page.getByRole("button", { name: "安全登录" }).click();
  await expect(
    page.getByRole("heading", { name: "管理控制台", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".source-card").first()).toBeVisible();
  await page.getByRole("button", { name: "查看目录树" }).first().click();
  await expect(page.locator(".source-tree").first()).toBeVisible();
  for (const section of ["jobs", "review", "health", "admins", "audits"]) {
    await page.goto("/admin/" + section);
    await expect(
      page.getByRole("heading", { name: "管理控制台", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".loading-line")).toHaveCount(0);
    await expect(page.locator(".error-banner")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.goto("/admin/suggestions");
  const suggestion = page
    .locator(".suggestion-card")
    .filter({ hasText: proposedTitle });
  await expect(suggestion).toBeVisible();
  await suggestion
    .getByLabel("审核说明")
    .fill("本地浏览器集成验证，不修改公共资料");
  await suggestion.getByRole("button", { name: "驳回建议" }).click();
  await expect(suggestion.getByText("已驳回", { exact: true })).toBeVisible();
  await page.goto("/admin/import");
  await page
    .getByLabel("一次粘贴多条分享信息")
    .fill(
      "模拟影库 https://115.com/s/demoa?password=1234\n模拟剧集 https://115.com/s/demotv 访问码：5678",
    );
  await page.getByRole("button", { name: "解析并预览" }).click();
  await expect(page.locator(".preview-list article")).toHaveCount(2);
  await page.screenshot({
    path: `artifacts/import-${testInfo.project.name}.png`,
    fullPage: true,
  });
  expect(remoteRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});
