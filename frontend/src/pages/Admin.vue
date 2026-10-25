<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  api,
  post,
  patch,
  session,
  loadMe,
  notice,
  label,
  category,
  date,
  type Row,
} from "../api";
import SourceTree from "../components/SourceTree.vue";
const route = useRoute();
const router = useRouter();
const section = computed(() => String(route.params.section || "sources"));
const navigation = [
  ["sources", "分享来源", "i-lucide-folders"],
  ["import", "批量导入", "i-lucide-list-plus"],
  ["jobs", "任务队列", "i-lucide-list-todo"],
  ["review", "待确认", "i-lucide-scan-search"],
  ["health", "健康检测", "i-lucide-heart-pulse"],
  ["suggestions", "纠错审核", "i-lucide-messages-square"],
  ["audits", "操作日志", "i-lucide-history"],
  ["admins", "管理员", "i-lucide-users-round"],
];
const visibleNavigation = computed(() =>
  navigation.filter((i) => i[0] !== "admins" || session.user?.superuser),
);
function changeLabel(key: string | number) {
  return (
    (
      {
        title: "片名",
        year: "年份",
        poster: "海报网址",
        tmdb_url: "TMDB 条目",
        path: "目录路径",
        variant_id: "对应版本",
        category: "类别",
      } as Record<string, string>
    )[key] || key
  );
}
const title = computed(
  () => navigation.find((n) => n[0] === section.value)?.[1] || "分享来源",
);
const user = reactive({ username: "", password: "" });
const loginError = ref("");
const loginBusy = ref(false);
const data = ref<Row[]>([]);
const targets = ref<Row[]>([]);
const loading = ref(false);
const error = ref("");
const actionBusy = ref("");
const refreshing = ref(false);
const text = ref("");
const preview = ref<Row[]>([]);
const adapter = ref("mock");
const liveEnabled = ref(false);
const importing = ref(false);
const previewError = ref("");
const previewBlocked = computed(() =>
  preview.value.some((item) => item.conflict || item.error || !/^[A-Za-z0-9]{1,32}$/.test(String(item.access_code || ""))),
);
const selectedSource = ref<Row | null>(null);
const directorySelection = ref<{ source: Row; node: Row } | null>(null);
const directoryError = ref("");
async function indexDirectory() {
  const selected = directorySelection.value;
  if (!selected || actionBusy.value) return;
  actionBusy.value = "directory";
  directoryError.value = "";
  try {
    await post(`/admin/sources/${selected.source.id}/directories/${selected.node.id}/scan`);
    directorySelection.value = null;
    notice("指定目录已排队，仅直接子项、最多两次目录请求");
    await router.push("/admin/jobs");
  } catch (e) {
    directoryError.value = (e as Error).message;
  } finally {
    actionBusy.value = "";
  }
}
const editSource = ref<Row | null>(null);
const sourceForm = reactive({
  title: "",
  access_code: "",
  enabled: true,
  credential: "",
});
const reviewEdit = ref<Row | null>(null);
const reviewForm = reactive({
  title: "",
  year: "",
  category: "movie",
  poster: "",
  tmdb_url: "",
  path: "",
  variant_id: "",
  plot: "",
  actors: "",
  genres: "",
  visible: true,
});
const newAdmin = reactive({ username: "", password: "", superuser: false });
const showNewAdmin = ref(false);
const adminPassword = reactive<Record<string, string>>({});
const reviewReason = ref<Record<string, string>>({});
let loadGeneration = 0;
async function login() {
  loginBusy.value = true;
  loginError.value = "";
  try {
    await post("/login", user);
    await loadMe();
    user.password = "";
    await load();
  } catch (e) {
    loginError.value = (e as Error).message;
  } finally {
    loginBusy.value = false;
  }
}
async function logout() {
  try {
    await post("/logout");
    session.user = null;
    data.value = [];
    router.replace("/admin");
    notice("已安全退出");
  } catch (e) {
    notice((e as Error).message, true);
  }
}
async function load() {
  if (!session.user) return;
  const generation = ++loadGeneration;
  loading.value = true;
  error.value = "";
  selectedSource.value = null;
  try {
    if (section.value === "import") {
      const stats = await api("/stats");
      liveEnabled.value = Boolean(stats.live_enabled);
    }
    const paths: Record<string, string> = {
      sources: "/admin/sources",
      jobs: "/admin/jobs",
      review: "/admin/review",
      health: "/admin/health",
      suggestions: "/admin/suggestions",
      admins: "/admin/admins",
      audits: "/admin/audits",
    };
    const path = paths[section.value];
    if (path) {
      const res = await api(path);
      if (generation === loadGeneration) data.value = res.items || [];
    }
    if (section.value === "health") {
      const res = await api("/admin/health/targets");
      if (generation === loadGeneration) targets.value = res.items || [];
    }
  } catch (e) {
    if (generation === loadGeneration) error.value = (e as Error).message;
  } finally {
    if (generation === loadGeneration) loading.value = false;
  }
}
async function action(
  key: string,
  fn: () => Promise<unknown>,
  message: string,
) {
  if (actionBusy.value) return;
  actionBusy.value = key;
  try {
    await fn();
    notice(message);
    await load();
  } catch (e) {
    notice((e as Error).message, true);
  } finally {
    actionBusy.value = "";
  }
}
async function parse() {
  previewError.value = "";
  importing.value = true;
  try {
    preview.value =
      (await post("/admin/import/preview", { text: text.value })).items || [];
    if (!preview.value.length)
      previewError.value = "未识别到分享链接，请检查输入。";
  } catch (e) {
    previewError.value = (e as Error).message;
  } finally {
    importing.value = false;
  }
}
async function importSources() {
  importing.value = true;
  try {
    await post("/admin/import", {
      items: preview.value.map((p) => ({
        url: p.url,
        access_code: p.access_code,
        title: p.title,
      })),
      adapter: adapter.value,
      scan_mode: adapter.value === "live" ? "root_preview" : "full",
    });
    notice("分享已进入独立任务队列");
    preview.value = [];
    text.value = "";
    router.push("/admin/jobs");
  } catch (e) {
    notice((e as Error).message, true);
  } finally {
    importing.value = false;
  }
}
function openSource(source: Row) {
  editSource.value = source;
  Object.assign(sourceForm, {
    title: source.title,
    access_code: source.access_code || "",
    enabled: source.enabled,
    credential: "",
  });
}
async function saveSource() {
  await action(
    "source",
    async () => {
      const changes: Row = {
        title: sourceForm.title,
        access_code: sourceForm.access_code,
        enabled: sourceForm.enabled,
      };
      if (sourceForm.credential) changes.credential = sourceForm.credential;
      await patch("/admin/sources/" + editSource.value!.id, changes);
      editSource.value = null;
      sourceForm.credential = "";
    },
    "来源配置已保存",
  );
}
function openReview(work: Row) {
  reviewEdit.value = work;
  Object.assign(reviewForm, {
    title: work.title || "",
    year: work.year ? String(work.year) : "",
    category: work.category || "movie",
    poster: work.info?.poster || "",
    tmdb_url: work.info?.tmdb_url || "",
    path: "",
    variant_id: "",
    plot: work.info?.plot || "",
    actors: (work.info?.actors || []).join("、"),
    genres: (work.info?.genres || []).join("、"),
    visible: work.visible !== false,
  });
}
async function saveReview() {
  await action(
    "review",
    async () => {
      if (!reviewForm.title.trim()) throw new Error("请填写可以识别的作品名称");
      const fields: Row = {
        ...reviewForm,
        title: reviewForm.title.trim(),
        year: reviewForm.year ? Number(reviewForm.year) : null,
        status: "confirmed",
        actors: reviewForm.actors
          .split(/[、,，\n]/)
          .map((x) => x.trim())
          .filter(Boolean),
        genres: reviewForm.genres
          .split(/[、,，\n]/)
          .map((x) => x.trim())
          .filter(Boolean),
      };
      if (!fields.path) {
        delete fields.path;
        delete fields.variant_id;
      } else {
        if (!reviewForm.variant_id) throw new Error("请指定需要纠正路径的版本");
        fields.variant_id = Number(reviewForm.variant_id);
      }
      // Confirming metadata alone must not silently lock an automatic poster.
      if (fields.poster === (reviewEdit.value!.info?.poster || "")) delete fields.poster;
      await patch("/admin/works/" + reviewEdit.value!.id, fields);
      reviewEdit.value = null;
    },
    "资料已确认，人工字段将保留",
  );
}
async function createAdmin() {
  await action(
    "admin",
    async () => {
      await post("/admin/admins", newAdmin);
      newAdmin.username = "";
      newAdmin.password = "";
      showNewAdmin.value = false;
    },
    "管理员已创建",
  );
}
async function updateAdminAccount(item: Row, changes: Row, message: string) {
  await action(
    "admin-update-" + item.id,
    () => patch("/admin/admins/" + item.id, changes),
    message,
  );
  if (changes.password) adminPassword[String(item.id)] = "";
}
async function recheck(target: Row) {
  await action(
    "check" + target.id,
    () =>
      post("/admin/recheck", {
        source_id: target.source_id || target.id,
        ...(target.scope === "node" || target.node_id
          ? { node_id: target.node_id || target.id }
          : {}),
      }),
    "复检已排队，不会立即判定失效",
  );
}
onMounted(async () => {
  if (!session.ready) await loadMe();
  load();
});
watch(section, () => {
  data.value = [];
  load();
});
watch(
  () => session.user,
  () => {
    if (session.user) load();
  },
);
</script>
<template>
  <section v-if="!session.ready" class="state-panel">正在检查登录状态…</section>
  <section v-else-if="!session.user" class="login-layout">
    <div class="login-copy">
      <p class="eyebrow">THE ARCHIVE, BEHIND THE SCENES</p>
      <h1>让庞杂有序，<br />让每个版本可寻。</h1>
      <p class="lead">
        来源独立管理，作品公共归档。<br />只读索引，不改变原分享的任何文件。
      </p>
      <div class="login-features">
        <span><UIcon name="i-lucide-shield-check" />管理员来源隔离</span
        ><span><UIcon name="i-lucide-workflow" />持久任务与断点续跑</span
        ><span><UIcon name="i-lucide-heart-pulse" />目录与文件独立复检</span>
      </div>
    </div>
    <form class="panel login-panel" @submit.prevent="login">
      <span class="login-icon"><UIcon name="i-lucide-key-round" /></span>
      <h2>登录管理控制台</h2>
      <p class="muted">使用本地初始化时创建的管理员账号。</p>
      <label for="username"
        >用户名<input
          id="username"
          v-model="user.username"
          required
          autocomplete="username"
          maxlength="80" /></label
      ><label for="password"
        >密码<input
          id="password"
          v-model="user.password"
          required
          type="password"
          autocomplete="current-password"
      /></label>
      <p v-if="loginError" class="inline-error" role="alert">
        {{ loginError }}
      </p>
      <UButton type="submit" size="lg" block :loading="loginBusy"
        >安全登录 <UIcon name="i-lucide-arrow-right"
      /></UButton>
      <p class="small muted">未开放访客注册。账号由超级管理员管理。</p>
    </form>
  </section>
  <template v-else
    ><div class="admin-heading">
      <div>
        <p class="eyebrow">WORKSPACE / READ-ONLY INDEX</p>
        <h1>管理控制台</h1>
      </div>
      <div class="account-info">
        <UIcon name="i-lucide-user-round" /><span
          >{{ session.user.username
          }}<small>{{
            session.user.superuser ? "超级管理员" : "来源管理员"
          }}</small></span
        ><UButton color="neutral" variant="outline" @click="logout"
          >退出登录</UButton
        >
      </div>
    </div>
    <div class="admin-layout">
      <aside class="admin-sidebar">
        <nav aria-label="后台功能">
          <RouterLink
            v-for="item in visibleNavigation"
            :key="item[0]"
            :to="'/admin/' + item[0]"
            :class="{ active: section === item[0] }"
            ><UIcon :name="item[2]" />{{ item[1] }}</RouterLink
          >
        </nav>
        <div class="sidebar-note">
          <UIcon name="i-lucide-lock-keyhole" />
          <p>只读适配器<br />不调用转存及写入接口</p>
        </div>
      </aside>
      <div class="admin-content">
        <div class="section-heading">
          <h2>{{ title }}</h2>
          <UButton
            v-if="section !== 'import'"
            color="neutral"
            variant="outline"
            icon="i-lucide-refresh-cw"
            :loading="loading || refreshing"
            @click="load"
            >刷新</UButton
          >
        </div>
        <div v-if="error" class="error-banner" role="alert">
          <UIcon name="i-lucide-circle-alert" />{{ error
          }}<UButton color="neutral" variant="ghost" @click="load"
            >重试</UButton
          >
        </div>
        <p v-if="loading" class="loading-line" role="status">
          正在加载{{ title }}…
        </p>

        <template v-if="section === 'import'"
          ><div class="info-banner">
            <UIcon name="i-lucide-flask-conical" />
            <div>
              <strong>当前只使用模拟适配器</strong>
              <p>
                <template v-if="liveEnabled">服务端已授权真实目录读取。真实导入只预览根目录最多两页，不读取 NFO，不递归；不要求 Cookie，接口要求认证时会提示。</template>
                <template v-else>当前仅能导入 demoa、demob、demotv
                三个模拟分享码。粘贴只用于解析；扫描读取本地脱敏样本，不访问真实分享。
                </template>
              </p>
            </div>
          </div>
          <form class="panel import-panel" @submit.prevent="parse">
            <label for="share-text"
              >一次粘贴多条分享信息<textarea
                id="share-text"
                v-model="text"
                rows="8"
                required
                placeholder="示例：影片合集 https://115.com/s/demoa?password=1234&#10;剧集合集 https://115.com/s/demotv 访问码：5678"
              />
            </label>
            <p class="small muted">
              支持 password 参数、独立访问码与混合文案。每个链接独立生成任务。
            </p>
            <p v-if="previewError" class="inline-error" role="alert">
              {{ previewError }}
            </p>
            <UButton
              type="submit"
              icon="i-lucide-scan-text"
              :loading="importing"
              >解析并预览</UButton
            >
          </form>
          <section v-if="preview.length" class="panel">
            <h3>
              导入预览
              <span class="heading-count">{{ preview.length }} 条</span>
            </h3>
            <p class="muted small">
              确认链接与访问码，冲突或缺失时请修正后再导入。
            </p>
            <div class="preview-list">
              <article v-for="(item, i) in preview" :key="i">
                <span class="row-index">{{
                  String(i + 1).padStart(2, "0")
                }}</span>
                <div>
                  <label
                    >来源名称<input
                      v-model="item.title"
                      placeholder="选填备注名称" /></label
                  ><label
                    >原分享链接<input v-model="item.url" type="url" required
                  /></label>
                  <p
                    v-if="item.warning || item.error || item.conflict"
                    class="inline-error"
                  >
                    {{ item.warning || item.error || "访问码冲突，请手动核对" }}
                  </p>
                </div>
                <label
                  >访问码<input
                    v-model="item.access_code"
                    maxlength="16"
                    placeholder="无访问码" /></label
                ><UButton
                  color="neutral"
                  variant="ghost"
                  aria-label="移除此条分享"
                  icon="i-lucide-x"
                  @click="preview.splice(i, 1)"
                />
              </article>
            </div>
            <div class="form-actions">
              <label
                >读取适配器<select v-model="adapter">
                  <option value="mock">模拟目录（不会访问 115）</option>
                  <option :disabled="!liveEnabled" value="live">真实 115（需服务端授权，仅根目录预览）</option>
                </select></label
              ><UButton
                :loading="importing"
                :disabled="previewBlocked"
                icon="i-lucide-list-plus"
                @click="importSources"
                >确认导入 {{ preview.length }} 个来源</UButton
              >
              <p v-if="previewBlocked" class="inline-error" role="alert">
                请先修正冲突、无效或缺少访问码的条目。
              </p>
            </div>
          </section></template
        >

        <template v-else-if="section === 'sources'"
          ><p class="section-description">
            这里只显示你有权管理的分享来源。公共作品库可合并展示，但源配置与凭据独立隔离。
          </p>
          <div v-if="!loading && !data.length" class="state-panel">
            <UIcon name="i-lucide-folder-plus" />
            <h3>从第一个分享来源开始</h3>
            <p>批量粘贴分享文案后，系统将独立排队建立目录索引。</p>
            <UButton to="/admin/import">批量导入</UButton>
          </div>
          <div class="source-list">
            <article
              v-for="source in data"
              :key="source.id"
              class="panel source-card"
            >
              <div class="source-card-heading">
                <span class="source-icon"
                  ><UIcon name="i-lucide-folder-closed"
                /></span>
                <div>
                  <h3>{{ source.title || source.code }}</h3>
                  <p class="small muted break-word">{{ source.url }}</p>
                </div>
                <UBadge color="neutral" variant="subtle">{{
                  source.adapter === "mock" ? "模拟来源" : "115 只读"
                }}</UBadge
                ><span class="health-badge" :data-state="source.health">{{
                  label(source.health)
                }}</span>
              </div>
              <div class="source-meta">
                <span
                  >访问码：<code>{{ source.access_code || "无" }}</code></span
                ><span>{{ source.enabled ? "已启用" : "已停用" }}</span
                ><span
                  >凭据：{{
                    source.has_credential ? "已加密保存" : "未配置"
                  }}</span
                ><span>最近扫描：{{ date(source.last_scan) }}</span>
                <span>目录访问：{{ label(source.access_status || "uncertain") }}</span>
              </div>
              <p v-if="source.adapter === 'live'" class="small muted">
                公开目录可免登录读取；NFO 等私有操作需要账号凭据。根目录预览最多两页，不递归。
              </p>
              <div class="button-row">
                <UButton
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-folder-tree"
                  @click="
                    selectedSource =
                      selectedSource?.id === source.id ? null : source
                  "
                  >{{
                    selectedSource?.id === source.id ? "收起目录" : "查看目录树"
                  }}</UButton
                ><UButton
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-settings-2"
                  @click="openSource(source)"
                  >编辑来源</UButton
                ><UButton
                  color="neutral"
                  variant="ghost"
                  :loading="actionBusy === 'scan' + source.id"
                  @click="
                    action(
                      'scan' + source.id,
                      () => post('/admin/sources/' + source.id + '/scan'),
                      '扫描已排队',
                    )
                  "
                  >重新扫描</UButton
                ><UButton
                  color="neutral"
                  variant="ghost"
                  @click="recheck({ ...source, scope: 'source' })"
                  >复检分享</UButton
                >
              </div>
              <div
                v-if="selectedSource?.id === source.id"
                class="tree-container"
              >
                <p class="small muted">
                  按需加载已入库节点；不会在浏览目录时扫描真实资源。
                </p>
                <SourceTree :source-id="source.id" @index="directorySelection = { source, node: $event }; directoryError = ''" />
              </div>
            </article>
          </div>
          <section v-if="directorySelection" class="panel edit-panel" aria-labelledby="directory-confirm-heading">
            <h3 id="directory-confirm-heading">确认指定子目录索引</h3>
            <p class="tree-path">{{ directorySelection.node.path }}</p>
            <p>仅索引此目录的直接子项，不递归。最多两次目录分页请求，失败也会消耗预算；暂停、重试和重启不重置。</p>
            <p class="small muted">完成仅表示限定范围结束，不代表整个分享入库。真实来源不读取 NFO、海报或影视内容。</p>
            <p v-if="directoryError" role="alert">{{ directoryError }}</p>
            <div class="form-actions">
              <UButton class="min-h-11" :loading="actionBusy === 'directory'" @click="indexDirectory">确认索引此目录</UButton>
              <UButton class="min-h-11" color="neutral" variant="ghost" :disabled="actionBusy === 'directory'" @click="directorySelection = null">取消</UButton>
            </div>
          </section>
          <section v-if="editSource" class="panel edit-panel">
            <h3>编辑来源 · {{ editSource.title }}</h3>
            <form class="form-grid" @submit.prevent="saveSource">
              <label
                >来源名称<input
                  v-model="sourceForm.title"
                  required
                  maxlength="300" /></label
              ><label
                >访问码<input
                  v-model="sourceForm.access_code"
                  maxlength="16" /></label
              ><label class="full-width"
                >更新 115 凭据（留空保留现有值）<input
                  v-model="sourceForm.credential"
                  type="password"
                  autocomplete="new-password"
                  placeholder="仅服务器加密保存，永不返回前台" /></label
              ><label class="checkbox-label full-width"
                ><input
                  v-model="sourceForm.enabled"
                  type="checkbox"
                />启用此来源</label
              >
              <div class="form-actions full-width">
                <UButton type="submit" :loading="actionBusy === 'source'"
                  >保存配置</UButton
                ><UButton
                  color="neutral"
                  variant="ghost"
                  @click="
                    editSource = null;
                    sourceForm.credential = '';
                  "
                  >取消</UButton
                >
              </div>
            </form>
          </section></template
        >

        <template v-else-if="section === 'jobs'"
          ><p class="section-description">
            任务与分页检查点持久保存。部分目录失败会单独记录；暂停后可从检查点继续。
          </p>
          <div v-if="!loading && !data.length" class="state-panel">
            <UIcon name="i-lucide-list-todo" />
            <h3>暂无扫描任务</h3>
            <UButton to="/admin/import">导入分享</UButton>
          </div>
          <article v-for="job in data" :key="job.id" class="panel job-card">
            <div class="version-top">
              <div>
                <span class="small muted">任务 #{{ job.id }}</span>
                <h3>{{ job.title || "来源 " + job.source_id }}</h3>
                <p class="small muted">{{ label(job.scan_mode || 'full') }}</p>
                <p v-if="job.scan_mode === 'directory_preview'" class="tree-path">范围：{{ job.scope_path }}（仅直接子项）</p>
                <p v-if="job.request_limit" class="small muted">
                  目录请求 {{ job.scan_requests || 0 }} / {{ job.request_limit || 2 }}；
                  已返回 {{ job.pages_read || 0 }} 页、{{ job.nodes_read || 0 }} 个节点。
                  {{ (job.truncated || (job.status === 'partial' && job.scan_requests >= job.request_limit)) ? '部分返回／请求预算耗尽，不代表完整入库' : '不递归扫描' }}
                  {{ job.status === 'complete' ? '已完成限定范围，不代表整个分享入库。' : '' }}
                </p>
              </div>
              <span class="health-badge" :data-state="job.status">{{
                label(job.status)
              }}</span>
            </div>
            <div class="job-progress">
              <span
                :style="{
                  width:
                    (job.total
                      ? Math.min(100, (job.done / job.total) * 100)
                      : 0) + '%',
                }"
              />
            </div>
            <div class="job-stats">
              <span
                >已处理 <strong>{{ job.done || 0 }}</strong></span
              ><span
                >已知任务 <strong>{{ job.total ?? "未知" }}</strong></span
              ><span
                >等待 <strong>{{ job.queued || 0 }}</strong></span
              ><span
                >运行 <strong>{{ job.running || 0 }}</strong></span
              ><span
                >失败 <strong>{{ job.failed || 0 }}</strong></span
              >
            </div>
            <p class="small muted">
              {{ job.request_limit ? '仅处理限定目录的直接子项，不会递归。请求预算耗尽后不会自动续扫。' : '进度仅按当前已知任务计算；发现子目录后任务总量会增加。' }}
            </p>
            <p v-if="job.error" class="inline-error">{{ job.error }}</p>
            <details v-if="job.errors?.length">
              <summary>查看失败目录（{{ job.errors.length }}）</summary>
              <ul class="task-errors">
                <li v-for="issue in job.errors" :key="issue.id">
                  <code>{{ issue.target }}</code> {{ issue.error }}
                </li>
              </ul>
            </details>
            <div class="button-row">
              <UButton
                v-if="['queued', 'pending', 'running'].includes(job.status)"
                color="neutral"
                variant="outline"
                icon="i-lucide-pause"
                :loading="actionBusy === job.id + 'pause'"
                @click="
                  action(
                    job.id + 'pause',
                    () => post('/admin/jobs/' + job.id + '/pause'),
                    '任务已暂停',
                  )
                "
                >暂停</UButton
              ><UButton
                v-if="job.status === 'paused'"
                icon="i-lucide-play"
                :loading="actionBusy === job.id + 'resume'"
                @click="
                  action(
                    job.id + 'resume',
                    () => post('/admin/jobs/' + job.id + '/resume'),
                    '任务已继续',
                  )
                "
                >继续扫描</UButton
              ><UButton
                v-if="
                  ['partial', 'complete', 'completed'].includes(job.status) &&
                  job.failed > 0
                "
                color="neutral"
                variant="outline"
                icon="i-lucide-rotate-ccw"
                :loading="actionBusy === job.id + 'retry'"
                @click="
                  action(
                    job.id + 'retry',
                    () => post('/admin/jobs/' + job.id + '/retry'),
                    '失败任务已重新排队',
                  )
                "
                >重试失败目录</UButton
              ><UButton
                v-if="
                  [
                    'queued',
                    'pending',
                    'running',
                    'paused',
                    'partial',
                  ].includes(job.status)
                "
                color="neutral"
                variant="ghost"
                @click="
                  action(
                    job.id + 'cancel',
                    () => post('/admin/jobs/' + job.id + '/cancel'),
                    '任务已取消，现有索引保留',
                  )
                "
                >取消任务</UButton
              ><span class="small muted"
                >创建于 {{ date(job.created_at) }}</span
              >
            </div>
          </article></template
        >

        <template v-else-if="section === 'review'"
          ><p class="section-description">
            待确认作品仅在后台显示；管理员确认后才可公开。人工确认字段不会被自动识别覆盖。
          </p>
          <div v-if="!loading && !data.length" class="state-panel">
            <UIcon name="i-lucide-check-check" />
            <h3>没有待确认作品</h3>
            <p>新来源扫描识别后，低置信度项目会显示在这里。</p>
          </div>
          <div class="review-list">
            <article
              v-for="work in data"
              :key="work.id"
              class="panel review-card"
            >
              <div>
                <p class="eyebrow">
                  #{{ work.id }} · {{ category(work.category) }}
                </p>
                <h3>{{ work.title || "无法识别名称" }}</h3>
                <p class="small muted">
                  {{ work.year || "年份未知" }} ·
                  <span>待确认 · 仅后台可见</span>
                </p>
                <p class="small muted">海报来源：{{ label(work.info?.poster_source || 'placeholder') }} · {{ work.info?.poster_locked ? '人工锁定' : '未锁定' }}</p>
                <p v-if="work.review_reason || work.reason" class="small">
                  {{ work.review_reason || work.reason }}
                </p>
              </div>
              <UButton
                color="neutral"
                variant="outline"
                @click="openReview(work)"
                >编辑并确认</UButton
              >
            </article>
          </div>
          <section v-if="reviewEdit" class="panel edit-panel">
            <h3>确认作品资料 · #{{ reviewEdit.id }}</h3>
            <form class="form-grid" @submit.prevent="saveReview">
              <label
                >片名<input
                  v-model="reviewForm.title"
                  required
                  maxlength="300" /></label
              ><label
                >年份<input
                  v-model="reviewForm.year"
                  type="number"
                  min="1888"
                  max="2100" /></label
              ><label
                >作品类别<select v-model="reviewForm.category">
                  <option value="movie">电影</option>
                  <option value="tv">电视剧</option>
                  <option value="variety">综艺</option>
                  <option value="anime">动漫</option>
                  <option value="concert">演唱会</option>
                </select></label
              ><label
                >公开海报网址（修改后人工锁定）<input
                  v-model="reviewForm.poster"
                  type="url"
                  placeholder="https://…" /></label
              ><label class="full-width"
                >TMDB 条目网址<input
                  v-model="reviewForm.tmdb_url"
                  type="url"
                  placeholder="https://www.themoviedb.org/movie/…" /></label
              ><label class="full-width"
                >剧情简介<textarea
                  v-model="reviewForm.plot"
                  rows="3"
                  maxlength="10000"
                /></label
              ><label
                >演员（顿号或逗号分隔）<input
                  v-model="reviewForm.actors" /></label
              ><label
                >类型（顿号或逗号分隔）<input
                  v-model="reviewForm.genres" /></label
              ><label class="full-width"
                >目录纠错对应版本<select v-model="reviewForm.variant_id">
                  <option value="">请选择需要纠错的版本</option>
                  <option
                    v-for="variant in reviewEdit.variants || []"
                    :key="variant.id"
                    :value="String(variant.id)"
                  >
                    {{ variant.source_title || "来源" + variant.source_id }} ·
                    {{ variant.path }}
                  </option>
                </select></label
              ><label class="full-width"
                >纠正目录路径（选填）<input
                  v-model="reviewForm.path"
                  maxlength="4000" /></label
              ><label class="checkbox-label full-width"
                ><input
                  v-model="reviewForm.visible"
                  type="checkbox"
                />确认后允许前台显示</label
              >
              <div class="form-actions full-width">
                <UButton type="submit" :loading="actionBusy === 'review'"
                  >保存并确认</UButton
                ><UButton
                  color="neutral"
                  variant="ghost"
                  @click="reviewEdit = null"
                  >取消</UButton
                >
              </div>
            </form>
          </section></template
        >

        <template v-else-if="section === 'health'"
          ><div class="info-banner">
            <UIcon name="i-lucide-info" />
            <p>
              只有明确失效才累计失败次数。网络超时、限流、认证异常不会判定资源删除；默认
              3 次独立失败后隐藏。
            </p>
          </div>
          <h3 class="subheading">异常与待复检目标</h3>
          <div v-if="!targets.length && !loading" class="empty-inline">
            暂无异常目标。未检测不代表已确认有效。
          </div>
          <div class="table-scroll" v-if="targets.length">
            <table>
              <thead>
                <tr>
                  <th>范围</th>
                  <th>来源 / 路径</th>
                  <th>状态</th>
                  <th>明确失败</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="target in targets"
                  :key="target.scope + '-' + target.id"
                >
                  <td>
                    {{
                      ["source", "share"].includes(target.scope)
                        ? "分享"
                        : ["directory"].includes(target.scope) || target.is_dir
                          ? "目录"
                          : "文件"
                    }}
                  </td>
                  <td class="path-cell">
                    {{
                      target.source_title ||
                      target.title ||
                      target.path ||
                      target.id
                    }}
                  </td>
                  <td>{{ label(target.health) }}</td>
                  <td>{{ target.failures || 0 }}</td>
                  <td>
                    <UButton
                      color="neutral"
                      variant="outline"
                      size="sm"
                      @click="recheck(target)"
                      >手动复检</UButton
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <h3 class="subheading">检测历史</h3>
          <div v-if="!loading && !data.length" class="empty-inline">
            暂无检测记录。
          </div>
          <div v-if="data.length" class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>检测时间</th>
                  <th>目标</th>
                  <th>结果</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in data" :key="event.id">
                  <td>{{ date(event.at || event.created_at) }}</td>
                  <td class="path-cell">
                    {{
                      event.path ||
                      event.source_title ||
                      "来源 #" + event.source_id
                    }}
                  </td>
                  <td>{{ label(event.result || event.state) }}</td>
                  <td>{{ event.reason || "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div></template
        >

        <template v-else-if="section === 'suggestions'"
          ><p class="section-description">
            所有管理员均可审核公共资料建议。审核会记录前后值；不会赋予其他来源的私有配置权限。
          </p>
          <div v-if="!loading && !data.length" class="state-panel">
            <UIcon name="i-lucide-message-square-check" />
            <h3>暂无纠错建议</h3>
          </div>
          <article
            v-for="item in data"
            :key="item.id"
            class="panel suggestion-card"
          >
            <div class="version-top">
              <h3>
                建议 #{{ item.id }}
                <RouterLink :to="'/works/' + item.work_id"
                  >作品 #{{ item.work_id }}
                  <UIcon name="i-lucide-arrow-up-right"
                /></RouterLink>
              </h3>
              <span class="health-badge" :data-state="item.status">{{
                item.status === "pending" ? "待审核" : label(item.status)
              }}</span>
            </div>
            <dl class="suggestion-changes">
              <div v-for="(value, key) in item.changes" :key="key">
                <dt>{{ changeLabel(key) }}</dt>
                <dd>{{ value }}</dd>
              </div>
            </dl>
            <p class="small muted">提交于 {{ date(item.created_at) }}</p>
            <template v-if="['pending', 'submitted'].includes(item.status)"
              ><label
                >审核说明<input
                  v-model="reviewReason[item.id]"
                  placeholder="可选，记录采纳或驳回的原因"
                  maxlength="1000"
              /></label>
              <div class="button-row">
                <UButton
                  :loading="actionBusy === 'accept' + item.id"
                  @click="
                    action(
                      'accept' + item.id,
                      () =>
                        post('/admin/suggestions/' + item.id + '/review', {
                          accept: true,
                          reason: reviewReason[item.id] || '',
                        }),
                      '建议已采纳并记录审计',
                    )
                  "
                  >采纳修改</UButton
                ><UButton
                  color="neutral"
                  variant="outline"
                  :loading="actionBusy === 'reject' + item.id"
                  @click="
                    action(
                      'reject' + item.id,
                      () =>
                        post('/admin/suggestions/' + item.id + '/review', {
                          accept: false,
                          reason: reviewReason[item.id] || '',
                        }),
                      '建议已驳回',
                    )
                  "
                  >驳回建议</UButton
                >
              </div></template
            >
            <p v-else class="small muted">
              {{ item.reason || "此建议已完成审核。" }}
            </p>
          </article></template
        >

        <template v-else-if="section === 'admins'"
          ><p class="section-description">
            只有超级管理员可以创建后台账号。新管理员拥有独立来源空间；公共纠错由所有管理员审核。
          </p>
          <UButton
            icon="i-lucide-user-plus"
            @click="showNewAdmin = !showNewAdmin"
            >新增管理员</UButton
          >
          <form
            v-if="showNewAdmin"
            class="panel form-grid new-admin"
            @submit.prevent="createAdmin"
          >
            <label
              >用户名<input
                v-model="newAdmin.username"
                required
                autocomplete="off"
                minlength="3"
                maxlength="80" /></label
            ><label
              >初始密码<input
                v-model="newAdmin.password"
                type="password"
                required
                autocomplete="new-password"
                minlength="12"
                placeholder="至少 12 位" /></label
            ><label class="checkbox-label full-width"
              ><input
                v-model="newAdmin.superuser"
                type="checkbox"
              />授予超级管理员权限</label
            >
            <div class="form-actions full-width">
              <UButton type="submit" :loading="actionBusy === 'admin'"
                >创建账号</UButton
              ><UButton
                color="neutral"
                variant="ghost"
                @click="
                  showNewAdmin = false;
                  newAdmin.password = '';
                "
                >取消</UButton
              >
            </div>
          </form>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>权限</th>
                  <th>状态</th>
                  <th>创建时间</th>
                  <th>管理</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="admin in data" :key="admin.id">
                  <td>{{ admin.username }}</td>
                  <td>{{ admin.superuser ? "超级管理员" : "来源管理员" }}</td>
                  <td>{{ admin.active ? "启用" : "已停用" }}</td>
                  <td>{{ date(admin.created_at) }}</td>
                  <td>
                    <div class="button-row admin-actions">
                      <UButton
                        size="sm"
                        color="neutral"
                        variant="outline"
                        :disabled="admin.id === session.user?.id"
                        @click="
                          updateAdminAccount(
                            admin,
                            { active: !admin.active },
                            admin.active ? '管理员已停用' : '管理员已启用',
                          )
                        "
                        >{{ admin.active ? "停用" : "启用" }}</UButton
                      ><input
                        v-model="adminPassword[String(admin.id)]"
                        class="admin-password"
                        type="password"
                        minlength="12"
                        maxlength="200"
                        autocomplete="new-password"
                        placeholder="重置密码" /><UButton
                        size="sm"
                        color="neutral"
                        variant="ghost"
                        :disabled="String(adminPassword[admin.id] || '').length < 12"
                        @click="
                          updateAdminAccount(
                            admin,
                            { password: adminPassword[String(admin.id)] },
                            '密码已重置，已有会话已撤销',
                          )
                        "
                        >重置</UButton
                      >
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div></template
        >

        <template v-else-if="section === 'audits'"
          ><p class="section-description">
            记录管理员、来源配置与公共资料审核操作。不显示私有凭据。
          </p>
          <div v-if="!loading && !data.length" class="empty-inline">
            暂无操作日志。
          </div>
          <div v-if="data.length" class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作者</th>
                  <th>动作</th>
                  <th>对象</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in data" :key="item.id">
                  <td>{{ date(item.at || item.created_at) }}</td>
                  <td>
                    {{
                      item.username || item.actor_id || item.admin_id || "系统"
                    }}
                  </td>
                  <td>{{ item.action }}</td>
                  <td>
                    {{
                      item.target ||
                      (item.target_type || item.entity_type || "记录") +
                        " #" +
                        (item.target_id || item.entity_id || "—")
                    }}
                  </td>
                  <td class="path-cell">
                    <details>
                      <summary>展开记录</summary>
                      <pre>{{
                        JSON.stringify(
                          item.details ||
                            item.changes || {
                              before: item.before,
                              after: item.after,
                            },
                          null,
                          2,
                        )
                      }}</pre>
                    </details>
                  </td>
                </tr>
              </tbody>
            </table>
          </div></template
        >
      </div>
    </div></template
  >
</template>
