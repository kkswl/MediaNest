import { test, expect, type Page } from "@playwright/test";
const work = {
  id: 1,
  title: "山海之间",
  year: 2024,
  category: "movie",
  status: "confirmed",
  info: { plot: "这是仅用于本地验证的模拟电影资料。" },
  people: [{ id: 1, name: "林远" }],
  collections: [{ id: 1, name: "山海系列", kind: "series" }],
  variant_count: 2,
};
const variants = [
  {
    id: 1,
    source_id: 1,
    node_id: 10,
    path: "电影/山海之间 (2024)/4K/山海之间.mkv",
    name: "山海之间.2024.4K.mkv",
    size: 10240000000,
    share_url: "https://115.com/s/demo",
    access_code: "1234",
    source_title: "模拟影库",
    health: "ok",
    checked_at: "2026-10-23T00:00:00Z",
    attributes: {
      resolution: "4K",
      language: "国语",
      subtitle: "外挂字幕",
      format: "MKV",
    },
  },
  {
    id: 2,
    source_id: 2,
    node_id: 11,
    path: "合集/山海之间/BDMV",
    name: "山海之间 原盘",
    size: 20000000000,
    share_url: "https://115.com/s/demo2",
    access_code: "5678",
    source_title: "模拟原盘库",
    health: "pending_recheck",
    attributes: { resolution: "1080P", format: "BDMV" },
  },
];
async function mock(page: Page, admin = false) {
  let loggedIn=admin;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api", "");
    let result: unknown = { items: [] };
    let status = 200;
    if(path==='/login'){loggedIn=true;result={id:1,username:'demo_admin',superuser:true}}
    else if(path==='/logout'){loggedIn=false;result={ok:true}}
    else if (path === "/me") {
      result = loggedIn
        ? { id: 1, username: "demo_admin", superuser: true }
        : { detail: "未登录" };
      status = loggedIn ? 200 : 401;
    } else if (path === "/stats")
      result = {
        works: 1,
        variants: 2,
        sources: 2,
        review: 1,
        mock: true,
        live_enabled: false,
      };
    else if (path === "/catalog")
      result = { items: [work], total: 1, page: 1, page_size: 18 };
    else if (path === "/works/1") result = { ...work, variants };
    else if (path === "/people")
      result = { items: [{ id: 1, name: "林远", count: 1 }] };
    else if (path === "/collections")
      result = {
        items: [{ id: 1, name: "山海系列", kind: "series", count: 1 }],
      };
    else if (path === "/suggestions") result = { id: 1, status: "pending" };
    else if (path === "/admin/sources")
      result = {
        items: [
          {
            id: 1,
            title: "模拟影库",
            code: "demo",
            url: "https://115.com/s/demo",
            access_code: "1234",
            adapter: "mock",
            enabled: true,
            has_credential: false,
            health: "ok",
          },
        ],
      };
    else if (path.endsWith("/nodes"))
      result = {
        items: [
          {
            id: 10,
            remote_id: "10",
            name: "山海之间 (2024)",
            path: "电影/山海之间 (2024)",
            is_dir: true,
            health: "ok",
          },
        ],
      };
    else if (path === "/admin/import/preview")
      result = {
        items: [
          {
            url: "https://115.com/s/demo",
            access_code: "1234",
            title: "模拟影库",
          },
        ],
      };
    else if (path === "/admin/jobs")
      result = {
        items: [
          {
            id: 1,
            source_id: 1,
            title: "模拟影库",
            status: "paused",
            done: 10,
            total: 20,
            failed: 0,
            queued: 10,
            running: 0,
            created_at: "2026-10-23T00:00:00Z",
          },
        ],
      };
    else if (path === "/admin/review")
      result = {
        items: [
          {
            ...work,
            id: 2,
            title: "待确认影片",
            status: "review",
            visible: false,
          },
        ],
      };
    else if (path === "/admin/health/targets")
      result = {
        items: [
          {
            scope: "node",
            id: 10,
            source_id: 1,
            path: "电影/山海之间.mkv",
            health: "pending_recheck",
            failures: 1,
          },
        ],
      };
    else if (path === "/admin/health")
      result = {
        items: [
          {
            id: 1,
            source_id: 1,
            path: "电影/山海之间.mkv",
            result: "timeout",
            reason: "模拟网络超时，不累计失效",
            at: "2026-10-23T00:00:00Z",
          },
        ],
      };
    else if (path === "/admin/suggestions")
      result = {
        items: [
          {
            id: 1,
            work_id: 1,
            changes: { year: 2023 },
            status: "pending",
            created_at: "2026-10-23T00:00:00Z",
          },
        ],
      };
    else if (path === "/admin/admins")
      result = { items: [{ id: 1, username: "demo_admin", superuser: true }] };
    else if (path === "/admin/audits")
      result = {
        items: [
          {
            id: 1,
            username: "demo_admin",
            action: "approve_suggestion",
            target_type: "work",
            target_id: 1,
            at: "2026-10-23T00:00:00Z",
            details: { before: { year: 2024 }, after: { year: 2023 } },
          },
        ],
      };
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(result),
    });
  });
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
}
test("catalog filters and responsive navigation", async ({ page }, testInfo) => {
  await mock(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "山海之间" })).toBeVisible();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.locator('.brand-mark .iconify')).toBeVisible();
  await page.screenshot({path:`artifacts/offline-catalog-${testInfo.project.name}.png`,fullPage:true});
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page.getByLabel("清晰度")).toBeVisible();
  await page.getByLabel("清晰度").selectOption("4K");
  await page.getByRole("button", { name: "应用筛选" }).click();
  await expect(page).toHaveURL(/resolution=4K/);
  await noOverflow(page);
  await page.getByRole("link", { name: "演员", exact: true }).click();
  await expect(page.getByRole("heading", { name: "林远" })).toBeVisible();
  await noOverflow(page);
});
test('administrator login and logout are wired',async({page})=>{
 await mock(page);await page.goto('/admin');await page.getByLabel('用户名',{exact:true}).fill('demo_admin');await page.getByLabel('密码',{exact:true}).fill('demo-password-2026');await page.getByRole('button',{name:'安全登录'}).click();await expect(page.getByRole('heading',{name:'管理控制台',exact:true})).toBeVisible();await page.getByRole('button',{name:'退出登录'}).click();await expect(page.getByRole('heading',{name:'登录管理控制台'})).toBeVisible();
});
test("detail preserves versions and submits targeted correction", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/works/1");
  await expect(
    page.getByRole("heading", { name: "山海之间", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("电影/山海之间 (2024)/4K/山海之间.mkv", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "复制完整路径" })).toHaveCount(
    2,
  );
  await page.getByRole("button", { name: "提交资料纠错" }).click();
  await page.getByLabel("正确年份").fill("2023");
  const sent = page.waitForRequest(
    (r) => r.url().endsWith("/api/suggestions") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "提交审核" }).click();
  expect((await sent).postDataJSON()).toEqual({
    work_id: 1,
    changes: { year: 2023 },
  });
  await expect(page.getByRole("status")).toContainText("建议已提交");
  await noOverflow(page);
});
test("backend source tree, import preview, and task controls", async ({
  page,
}) => {
  await mock(page, true);
  await page.goto("/admin/sources");
  await expect(
    page.getByRole("heading", { name: "模拟影库", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看目录树" }).click();
  await expect(
    page.getByRole("button", { name: "山海之间 (2024)" }),
  ).toBeVisible();
  await noOverflow(page);
  await page.getByRole("link", { name: "批量导入", exact: true }).click();
  await page
    .getByLabel("一次粘贴多条分享信息")
    .fill("模拟影库 https://115.com/s/demo?password=1234");
  await page.getByRole("button", { name: "解析并预览" }).click();
  await expect(page.getByLabel("访问码", { exact: true })).toHaveValue("1234");
  await noOverflow(page);
  await page.getByRole("link", { name: "任务队列", exact: true }).click();
  await expect(page.getByRole("button", { name: "继续扫描" })).toBeVisible();
  const sent = page.waitForRequest((r) =>
    r.url().endsWith("/admin/jobs/1/resume"),
  );
  await page.getByRole("button", { name: "继续扫描" }).click();
  await sent;
  await noOverflow(page);
});
test("moderation, review, health, admins and audits render without overflow", async ({
  page,
}) => {
  await mock(page, true);
  for (const path of ["review", "health", "suggestions", "admins", "audits"]) {
    await page.goto("/admin/" + path);
    await expect(
      page.getByRole("heading", { name: "管理控制台", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "正在加载" +
          {
            review: "待确认",
            health: "健康检测",
            suggestions: "纠错审核",
            admins: "管理员",
            audits: "操作日志",
          }[path] +
          "…",
      ),
    ).toHaveCount(0);
    await noOverflow(page);
  }
  await page.goto("/admin/suggestions");
  await page.getByLabel("审核说明").fill("核对后采纳");
  const sent = page.waitForRequest(
    (r) => r.url().endsWith("/review") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "采纳修改" }).click();
  expect((await sent).postDataJSON()).toEqual({
    accept: true,
    reason: "核对后采纳",
  });
});
test("network error is actionable and reduced motion is supported", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/catalog?**", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "模拟网络故障" }),
    }),
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "暂时无法加载作品" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible();
  await noOverflow(page);
});
