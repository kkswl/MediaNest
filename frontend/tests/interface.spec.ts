import { test, expect, type Page } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) => {
    const host = new URL(route.request().url()).hostname;
    return host === '127.0.0.1' || host === 'localhost' ? route.fallback() : route.abort();
  });
});
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
    source_access_status: "public_listing",
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
    source_access_status: "credential_required",
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
            access_status: "public_listing",
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
            scan_mode: "root_preview",
            scan_requests: 1,
            request_limit: 2,
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
  await page.screenshot({path:testInfo.outputPath('offline-catalog.png'),fullPage:true});
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
  await expect(page.getByText('公开目录', { exact: true })).toBeVisible();
  await expect(page.getByText('需要账号凭据', { exact: true })).toBeVisible();
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
  await expect(page.getByText('目录访问：公开目录', { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "山海之间 (2024)", exact: true }),
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
test("directory indexing requires explicit scope confirmation", async ({ page }, testInfo) => {
  if (testInfo.project.name === "mobile") await page.setViewportSize({ width: 375, height: 812 });
  await mock(page, true);
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") writes.push(request.url());
  });
  await page.goto("/admin/sources");
  await page.getByRole("button", { name: "查看目录树" }).click();
  const index = page.getByRole("button", { name: "索引此目录：电影/山海之间 (2024)", exact: true });
  await expect(index).toBeVisible();
  expect((await index.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(writes).toHaveLength(0);
  await index.click();
  await expect(page.getByRole("heading", { name: "确认指定子目录索引" })).toBeVisible();
  await expect(page.getByText("仅索引此目录的直接子项", { exact: false })).toBeVisible();
  await noOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("directory-confirmation.png"), fullPage: true });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(writes).toHaveLength(0);
  await index.click();
  const sent = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/directories/10/scan"));
  await page.getByRole("button", { name: "确认索引此目录", exact: true }).click();
  await sent;
  await expect(page).toHaveURL(/\/admin\/jobs$/);
  expect(writes.filter(url => url.endsWith("/directories/10/scan"))).toHaveLength(1);
  await noOverflow(page);
});

test("bounded job states show scope, counts and truncation honestly", async ({ page }) => {
  await mock(page, true);
  await page.route("**/api/admin/jobs", route => route.fulfill({ json: { items: [{
    id: 2, title: "模拟限定目录", scan_mode: "directory_preview", status: "complete",
    scope_path: "模拟合集/" + "很长的模拟目录名称".repeat(15), request_limit: 2,
    scan_requests: 2, pages_read: 2, nodes_read: 4, truncated: true, total: 1, done: 1,
  }] } }));
  await page.goto("/admin/jobs");
  await expect(page.getByText("指定子目录索引（最多两次请求）", { exact: true })).toBeVisible();
  await expect(page.getByText(/目录请求 2 \/ 2； 已返回 2 页、4 个节点/)).toBeVisible();
  await expect(page.getByText(/已完成限定范围，不代表整个分享入库/)).toBeVisible();
  await noOverflow(page);
  await page.route("**/api/admin/jobs", route => route.fulfill({ json: { items: [{
    id: 3, title: "模拟失败任务", scan_mode: "directory_preview", status: "partial",
    scope_path: "模拟目录", request_limit: 2, scan_requests: 2, pages_read: 0, nodes_read: 0,
    truncated: false, total: 1, done: 0, failed: 1,
  }] } }));
  await page.reload();
  await expect(page.getByText(/部分返回／请求预算耗尽，不代表完整入库/)).toBeVisible();
  await expect(page.getByText(/已完成限定范围，不代表整个分享入库/)).toHaveCount(0);
});

test("review queue is private and unchanged automatic poster is not locked", async ({ page }) => {
  await mock(page, true);
  await page.goto("/admin/review");
  await expect(page.getByText("待确认 · 仅后台可见", { exact: true })).toBeVisible();
  await expect(page.getByText("海报来源：默认占位图 · 未锁定", { exact: true })).toBeVisible();
  await expect(page.getByText("前台：信息待完善")).toHaveCount(0);
  await page.getByRole("button", { name: "编辑并确认" }).click();
  const sent = page.waitForRequest((r) => r.method() === "PATCH" && r.url().endsWith("/admin/works/2"));
  await page.getByRole("button", { name: "保存并确认", exact: true }).click();
  const fields = (await sent).postDataJSON();
  expect(fields.status).toBe("confirmed");
  expect(fields).not.toHaveProperty("poster");
  await noOverflow(page);
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
