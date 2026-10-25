<script setup lang="ts">
import { onMounted, ref, reactive, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, category, type Row } from "../api";
import WorkCard from "../components/WorkCard.vue";
const route = useRoute();
const router = useRouter();
const filters = reactive<Record<string, string>>({
  q: "",
  category: "",
  year: "",
  resolution: "",
  language: "",
  subtitle: "",
  format: "",
  genre: "",
  person: "",
  collection: "",
});
const works = ref<Row[]>([]);
const stats = ref<Row>({});
const total = ref(0);
const page = ref(1);
const busy = ref(true);
const error = ref("");
const expanded = ref(false);
let request = 0;
async function load() {
  const id = ++request;
  busy.value = true;
  error.value = "";
  try {
    const p = new URLSearchParams({
      page: String(page.value),
      page_size: "18",
    });
    Object.entries(filters).forEach(([k, v]) => {
      if (v) p.set(k, v);
    });
    const data = await api("/catalog?" + p);
    if (id === request) {
      works.value = data.items;
      total.value = data.total;
    }
  } catch (e) {
    if (id === request) error.value = (e as Error).message;
  } finally {
    if (id === request) busy.value = false;
  }
}
function apply() {
  page.value = 1;
  const q: Record<string, string> = {};
  Object.entries(filters).forEach(([k, v]) => {
    if (v) q[k] = v;
  });
  router.replace({ path: "/", query: q });
}
function clear() {
  Object.keys(filters).forEach((k) => (filters[k] = ""));
  apply();
}
watch(
  () => route.query,
  () => {
    Object.keys(filters).forEach(
      (k) => (filters[k] = String(route.query[k] || "")),
    );
    load();
  },
  { immediate: true },
);
onMounted(async () => {
  try {
    stats.value = await api("/stats");
  } catch {
    /* catalog handles connection errors */
  }
});
</script>
<template>
  <section class="discovery-heading">
    <div>
      <p class="eyebrow"><span class="live-dot" /> PERSONAL CINEMA ARCHIVE</p>
      <h1>每一个版本，<br />都有迹可循<span>。</span></h1>
      <p class="lead">
        把庞杂的分享目录，整理成清晰的影视世界。<br
          class="desktop-only"
        />按作品发现，按版本选择，循路径找到。
      </p>
    </div>
    <aside class="index-summary">
      <span class="summary-icon"><UIcon name="i-lucide-library-big" /></span>
      <div>
        <strong>{{ stats.works ?? "—" }}</strong
        ><span>已收录作品</span>
      </div>
      <div>
        <strong>{{ stats.variants ?? "—" }}</strong
        ><span>保留全部版本</span>
      </div>
      <p><UIcon name="i-lucide-shield-check" />只建立索引，不搬动原文件</p>
    </aside>
  </section>
  <div v-if="stats.mock" class="demo-strip">
    <UIcon name="i-lucide-flask-conical" /><span
      >本地模拟资料 · 未扫描真实 115 分享，抽象封面不是官方海报</span
    >
  </div>
  <section class="catalog-controls" aria-label="资源搜索与筛选">
    <form class="search-line" @submit.prevent="apply">
      <label for="search" class="sr-only">搜索片名、别名或目录</label>
      <div class="search-field">
        <UIcon name="i-lucide-search" /><input
          id="search"
          v-model="filters.q"
          type="search"
          placeholder="搜索片名、别名或目录…"
          autocomplete="off"
        />
      </div>
      <UButton type="submit" size="lg" icon="i-lucide-search">搜索资源</UButton
      ><UButton
        color="neutral"
        variant="outline"
        size="lg"
        :aria-expanded="expanded"
        aria-controls="advanced-filters"
        @click="expanded = !expanded"
        icon="i-lucide-sliders-horizontal"
        >筛选</UButton
      >
    </form>
    <div class="category-tabs" aria-label="作品分类">
      <button
        v-for="(name, key) in {
          '': '全部作品',
          movie: '电影',
          tv: '电视剧',
          variety: '综艺',
          anime: '动漫',
          concert: '演唱会',
        }"
        :key="key"
        :class="{ selected: filters.category === key }"
        :aria-pressed="filters.category === key"
        @click="
          filters.category = key;
          apply();
        "
      >
        {{ name }}
      </button>
    </div>
    <form
      v-show="expanded"
      id="advanced-filters"
      class="filter-grid"
      @submit.prevent="apply"
    >
      <label
        >影片类型<input
          v-model="filters.genre"
          list="genre-options"
          placeholder="如剧情、科幻" /><datalist id="genre-options">
          <option
            v-for="genre in [
              '剧情',
              '喜剧',
              '动作',
              '爱情',
              '科幻',
              '悬疑',
              '纪录',
            ]"
            :key="genre"
            :value="genre"
          /></datalist
      ></label>
      <label
        >年份<input
          v-model="filters.year"
          type="number"
          min="1888"
          max="2100"
          placeholder="全部年份" /></label
      ><label
        >清晰度<select v-model="filters.resolution">
          <option value="">全部清晰度</option>
          <option>4K</option>
          <option>1080P</option>
          <option>720P</option>
        </select></label
      ><label
        >语言<select v-model="filters.language">
          <option value="">全部语言</option>
          <option>国语</option>
          <option>原声</option>
          <option>未知</option>
        </select></label
      ><label
        >字幕<select v-model="filters.subtitle">
          <option value="">全部字幕</option>
          <option>外挂字幕</option>
          <option>内封字幕</option>
          <option>未知</option>
        </select></label
      ><label
        >格式<select v-model="filters.format">
          <option value="">全部格式</option>
          <option>ISO</option>
          <option>BDMV</option>
          <option>MKV</option>
          <option>MP4</option>
        </select></label
      >
      <div class="filter-actions">
        <UButton type="submit">应用筛选</UButton
        ><UButton color="neutral" variant="ghost" @click="clear">重置</UButton>
      </div>
    </form>
  </section>
  <section aria-labelledby="catalog-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">EXPLORE THE COLLECTION</p>
        <h2 id="catalog-title">
          {{ filters.category ? category(filters.category) : "发现好内容"
          }}<span class="heading-count">{{ total }} 部</span>
        </h2>
      </div>
      <span class="muted small">保留多版本 · 失效分层复检</span>
    </div>
    <div v-if="error" class="state-panel" role="alert">
      <UIcon name="i-lucide-wifi-off" />
      <h3>暂时无法加载作品</h3>
      <p>{{ error }}</p>
      <UButton @click="load">重新加载</UButton>
    </div>
    <div
      v-else-if="busy"
      class="poster-grid"
      aria-label="作品加载中"
      aria-busy="true"
    >
      <div v-for="i in 6" :key="i" class="skeleton-card">
        <div class="skeleton-poster" />
        <div class="skeleton-line" />
      </div>
    </div>
    <div v-else-if="!works.length" class="state-panel">
      <UIcon name="i-lucide-search-x" />
      <h3>还没有找到匹配的作品</h3>
      <p>试试其他片名或放宽筛选；新来源识别完成后会出现在这里。</p>
      <UButton color="neutral" variant="outline" @click="clear"
        >清除筛选</UButton
      >
    </div>
    <div v-else class="poster-grid">
      <WorkCard v-for="work in works" :key="work.id" :work="work" />
    </div>
    <div v-if="total > 18" class="pagination">
      <UButton
        color="neutral"
        variant="outline"
        :disabled="page === 1 || busy"
        @click="
          page--;
          load();
        "
        >上一页</UButton
      ><span>第 {{ page }} / {{ Math.ceil(total / 18) }} 页</span
      ><UButton
        color="neutral"
        variant="outline"
        :disabled="page * 18 >= total || busy"
        @click="
          page++;
          load();
        "
        >下一页</UButton
      >
    </div>
  </section>
</template>
