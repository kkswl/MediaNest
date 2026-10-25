import { reactive } from "vue";
export type Row = Record<string, any>;
export const session = reactive<{ user: Row | null; ready: boolean }>({
  user: null,
  ready: false,
});
export const feedback = reactive({ message: "", error: false });
let messageTimer: ReturnType<typeof setTimeout>;
export function notice(message: string, error = false) {
  feedback.message = message;
  feedback.error = error;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => (feedback.message = ""), 6000);
}
export async function api<T = Row>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  const csrf = document.cookie
    .split("; ")
    .find((x) => x.startsWith("csrf_token="))
    ?.split("=")[1];
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const res = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    let detail: any;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return res.status === 204 ? ({} as T) : await res.json();
}
export const post = (path: string, data: unknown = {}) =>
  api(path, { method: "POST", body: JSON.stringify(data) });
export const patch = (path: string, data: unknown) =>
  api(path, { method: "PATCH", body: JSON.stringify(data) });
export async function loadMe() {
  try {
    session.user = await api("/me");
  } catch {
    session.user = null;
  }
  session.ready = true;
}
export const categories: Record<string, string> = {
  movie: "电影",
  tv: "电视剧",
  series: "电视剧",
  variety: "综艺",
  anime: "动漫",
  concert: "演唱会",
  unknown: "待识别",
};
export const states: Record<string, string> = {
  pending: "待复检",
  queued: "排队中",
  running: "扫描中",
  paused: "已暂停",
  completed: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
  ok: "可用",
  healthy: "可用",
  valid: "可用",
  unknown: "未检测",
  pending_recheck: "待复检",
  recheck: "待复检",
  missing: "确认失效",
  invalid: "确认失效",
  hidden: "已隐藏",
  timeout: "网络超时",
  rate_limited: "请求受限",
  auth: "需认证",
  public_listing: "公开目录",
  credential_listing: "账号目录",
  credential_required: "需要账号凭据",
  auth_failed: "账号认证失败",
  root_preview: "根目录预览（最多两页）",
  directory_preview: "指定子目录索引（最多两次请求）",
  nfo: "源 NFO",
  directory: "作品目录海报",
  external: "外部备用海报",
  manual: "管理员指定",
  legacy_unknown: "旧数据／来源待确认",
  placeholder: "默认占位图",
  full: "完整索引",
  uncertain: "不确定",
  confirmed: "已确认",
  incomplete: "分页不完整",
  review: "待确认",
  accepted: "已采纳",
  rejected: "已驳回",
};
export function label(v: unknown) {
  return (
    (
      {
        complete: "已完成",
        share: "分享",
        directory: "目录",
        file: "文件",
        auth_required: "需要认证",
        not_found: "明确不存在",
        expired: "确认失效",
        unavailable: "暂不可用",
        network_error: "网络异常",
      } as Record<string, string>
    )[String(v)] ||
    states[String(v)] ||
    String(v ?? "未检测")
  );
}
export function category(v: unknown) {
  return categories[String(v)] || String(v ?? "待识别");
}
export function bytes(v: unknown) {
  let n = Number(v) || 0;
  const u = ["B", "KB", "GB", "TB", "PB"];
  const real = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (n >= 1024 && i < 5) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${real[i] || u[i]}`;
}
export function date(v: unknown) {
  if (!v) return "尚未记录";
  const d = new Date(
    typeof v === "number" ? (v < 1e12 ? v * 1000 : v) : String(v),
  );
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString("zh-CN");
}
export async function copy(v: string) {
  try {
    await navigator.clipboard.writeText(v);
    notice("已复制到剪贴板");
  } catch {
    notice("复制失败，请手动选择并复制", true);
  }
}
export function safeURL(v: unknown) {
  if (typeof v !== "string" || !v) return "";
  try {
    const u = new URL(v);
    return u.protocol === "https:" ? u.href : "";
  } catch {
    return "";
  }
}
export function posterOf(work: Row) {
  if (work.info && "poster" in work.info) return safeURL(work.info.poster);
  return safeURL(
    work.info?.poster ||
      work.info?.poster_public_url ||
      work.info?.poster_url ||
      work.poster_url ||
      work.poster,
  );
}
