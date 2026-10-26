<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  api,
  post,
  copy,
  notice,
  category,
  label,
  bytes,
  date,
  safeURL,
  type Row,
} from "../api";
import Poster from "../components/Poster.vue";
const route = useRoute();
const work = ref<Row | null>(null);
const busy = ref(true);
const error = ref("");
const correcting = ref(false);
const submitting = ref(false);
const suggestion = ref<Record<string, string>>({
  title: "",
  year: "",
  poster: "",
  tmdb_url: "",
  path: "",
});
const variantId = ref("");
const genres = computed(() => {
  const value = work.value?.info?.genres || work.value?.info?.genre || [];
  return Array.isArray(value) ? value : [value];
});
const metadata = computed(() => {
  const info = work.value?.info || {};
  return [
    [
      "导演",
      Array.isArray(info.directors) ? info.directors.join("、") : info.director,
    ],
    [
      "地区",
      Array.isArray(info.country) ? info.country.join("、") : info.country,
    ],
    ["时长", info.runtime ? `${info.runtime} 分钟` : ""],
    [
      "资料评分",
      info.rating
        ? `${info.rating}（${work.value?.provenance?.rating || "来源未标注"}）`
        : "",
    ],
  ].filter((item) => item[1]);
});
const externalLinks = computed(() => {
  const info = work.value?.info || {};
  const ids = info.external_ids || {};
  const links: { name: string; url: string }[] = [];
  const tmdb =
    safeURL(info.tmdb_url) ||
    (/^\d+$/.test(String(ids.tmdb))
      ? `https://www.themoviedb.org/${work.value?.category === "movie" ? "movie" : "tv"}/${ids.tmdb}`
      : "");
  if (tmdb) links.push({ name: "TMDB", url: tmdb });
  if (/^tt\d+$/.test(String(ids.imdb)))
    links.push({
      name: "IMDb",
      url: `https://www.imdb.com/title/${ids.imdb}/`,
    });
  if (/^\d+$/.test(String(ids.douban)))
    links.push({
      name: "豆瓣",
      url: `https://movie.douban.com/subject/${ids.douban}/`,
    });
  return links;
});
function fieldName(key: string | number) {
  return (
    (
      {
        title: "片名",
        year: "年份",
        original_title: "原名",
        plot: "简介",
        genres: "类型",
        actors: "演员",
        directors: "导演",
        poster: "海报",
        rating: "评分",
        country: "地区",
        external_ids: "外部标识",
        collection: "合集",
      } as Record<string, string>
    )[key] || key
  );
}
function scrollVersions() {
  document.getElementById("versions")?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
  });
}
const groups = computed(() => {
  const map = new Map<string, Row[]>();
  for (const v of work.value?.variants || []) {
    const key =
      v.season != null ? `第 ${v.season} 季` : v.resource_group || "全部版本";
    map.set(key, [...(map.get(key) || []), v]);
  }
  return [...map];
});
async function load() {
  busy.value = true;
  error.value = "";
  try {
    work.value = await api("/works/" + route.params.id);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
watch(() => route.params.id, load, { immediate: true });
async function submit() {
  submitting.value = true;
  try {
    const changes: Row = {};
    Object.entries(suggestion.value).forEach(([k, v]) => {
      const value = String(v ?? "").trim();
      if (value) changes[k] = k === "year" ? Number(value) : value;
    });
    if (!Object.keys(changes).length)
      throw new Error("请至少填写一项需要修改的信息");
    if (changes.path) {
      if (!variantId.value)
        throw new Error("纠正目录路径时，请选择对应的来源版本");
      changes.variant_id = Number(variantId.value);
    }
    await post("/suggestions", { work_id: work.value!.id, changes });
    notice("建议已提交，管理员审核后生效");
    correcting.value = false;
    suggestion.value = {
      title: "",
      year: "",
      poster: "",
      tmdb_url: "",
      path: "",
    };
    variantId.value = "";
  } catch (e) {
    notice((e as Error).message, true);
  } finally {
    submitting.value = false;
  }
}
function attributes(v: Row) {
  return Object.entries(v.attributes || {}).filter(
    ([k, val]) =>
      [
        "resolution",
        "language",
        "subtitle",
        "format",
        "codec",
        "hdr",
        "source",
        "audio_languages",
        "subtitle_languages",
      ].includes(k) &&
      ((typeof val === "string" && val) || (Array.isArray(val) && val.length)),
  ).map(([key, val]) => [
    key,
    Array.isArray(val) ? val.join("、") : val,
  ]);
}
</script>
<template>
  <RouterLink to="/" class="back-link"
    ><UIcon name="i-lucide-arrow-left" />返回作品库</RouterLink
  >
  <div v-if="busy" class="state-panel" aria-busy="true">正在读取作品信息…</div>
  <div v-else-if="error" class="state-panel" role="alert">
    <h2>作品暂不可用</h2>
    <p>{{ error }}</p>
    <UButton @click="load">重新加载</UButton>
  </div>
  <template v-else-if="work"
    ><section class="detail-hero">
      <div class="detail-poster"><Poster :work="work" /></div>
      <div class="detail-info">
        <p class="eyebrow">
          {{ category(work.category) }} / {{ work.year || "年份待完善" }}
        </p>
        <h1>{{ work.title }}</h1>
        <p
          v-if="work.info?.originaltitle || work.info?.original_title"
          class="original-title"
        >
          {{ work.info.originaltitle || work.info.original_title }}
        </p>
        <div class="badge-row">
          <UBadge color="primary" variant="subtle"
            >{{ (work.variants || []).length }} 个来源版本</UBadge
          ><UBadge
            v-if="work.status !== 'confirmed'"
            color="warning"
            variant="subtle"
            >信息待完善</UBadge
          ><UBadge
            v-for="genre in genres"
            :key="genre"
            color="neutral"
            variant="outline"
            >{{ genre }}</UBadge
          >
        </div>
        <p class="overview">
          {{
            work.info?.plot ||
            work.info?.overview ||
            "暂时没有剧情简介。当前资料来自目录与已有元数据，欢迎提交纠错建议。"
          }}
        </p>
        <dl v-if="metadata.length" class="metadata-grid">
          <div v-for="[key, value] in metadata" :key="key">
            <dt>{{ key }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <div v-if="externalLinks.length" class="external-links">
          <a
            v-for="link in externalLinks"
            :key="link.name"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
            >{{ link.name }} <UIcon name="i-lucide-external-link"
          /></a>
        </div>
        <div v-if="work.people?.length" class="detail-relations">
          <span>演员</span
          ><RouterLink
            v-for="person in work.people"
            :key="person.id"
            :to="{ path: '/', query: { person: person.id } }"
            >{{ person.name }}</RouterLink
          >
        </div>
        <div v-if="work.collections?.length" class="detail-relations">
          <span>合集</span
          ><RouterLink
            v-for="collection in work.collections"
            :key="collection.id"
            :to="{ path: '/', query: { collection: collection.id } }"
            >{{ collection.name }}</RouterLink
          >
        </div>
        <div class="detail-actions">
          <UButton
            icon="i-lucide-list-video"
            size="lg"
            @click="scrollVersions()"
            >查看来源版本</UButton
          ><UButton
            color="neutral"
            variant="outline"
            size="lg"
            icon="i-lucide-message-square-text"
            :aria-expanded="correcting"
            @click="correcting = !correcting"
            >提交资料纠错</UButton
          >
        </div>
        <p class="small muted">
          不播放、不转存。请根据完整路径在原分享中查找。
        </p>
        <p class="small muted">海报来源：{{ label(work.info?.poster_source || 'placeholder') }} · {{ work.info?.poster_locked ? '人工锁定' : '自动选择' }}</p>
        <details
          v-if="Object.keys(work.provenance || {}).length"
          class="provenance"
        >
          <summary>查看元数据来源</summary>
          <dl>
            <div v-for="(source, key) in work.provenance" :key="key">
              <dt>{{ fieldName(key) }}</dt>
              <dd>{{ source }}</dd>
            </div>
          </dl>
        </details>
      </div>
    </section>
    <section v-if="correcting" class="panel correction-panel">
      <h2>帮助完善作品信息</h2>
      <p class="muted">
        只填写需要修正的字段。建议不会直接修改页面，经管理员审核后生效。
      </p>
      <form class="form-grid" @submit.prevent="submit">
        <label
          >正确片名<input v-model="suggestion.title" maxlength="300" /></label
        ><label
          >正确年份<input
            v-model="suggestion.year"
            type="number"
            min="1888"
            max="2100" /></label
        ><label
          >公开海报网址<input
            v-model="suggestion.poster"
            type="url"
            placeholder="https://…" /></label
        ><label
          >TMDB 作品网址<input
            v-model="suggestion.tmdb_url"
            type="url"
            placeholder="https://www.themoviedb.org/movie/…" /></label
        ><label class="full-width"
          >目录纠错对应版本<select v-model="variantId">
            <option value="">请选择来源版本</option>
            <option
              v-for="v in work.variants || []"
              :key="v.id"
              :value="String(v.id)"
            >
              {{ v.source_title }} · {{ v.path }}
            </option>
          </select></label
        ><label class="full-width"
          >正确目录路径<textarea
            v-model="suggestion.path"
            rows="2"
            maxlength="4000"
          />
        </label>
        <div class="form-actions full-width">
          <UButton type="submit" :loading="submitting">提交审核</UButton
          ><UButton color="neutral" variant="ghost" @click="correcting = false"
            >取消</UButton
          >
        </div>
      </form>
    </section>
    <section id="versions">
      <div class="section-heading">
        <div>
          <p class="eyebrow">EVERY VERSION, EVERY SOURCE</p>
          <h2>来源与版本</h2>
        </div>
        <span class="small muted"
          >音轨、字幕可能来自文件名推断，请核对原目录</span
        >
      </div>
      <div v-if="!groups.length" class="state-panel">
        <h3>暂无可公开的有效版本</h3>
        <p>来源可能正在复检，请稍后再来。</p>
      </div>
      <section
        v-for="[group, variants] in groups"
        :key="group"
        class="version-group"
      >
        <h3>
          {{ group }}<span class="heading-count">{{ variants.length }} 个</span>
        </h3>
        <article v-for="v in variants" :key="v.id" class="version-card">
          <p v-if="v.is_demo" class="small muted">演示资源 · 虚构分享不提供外链</p>
          <div class="version-top">
            <h4>{{ v.name || v.resource_group || "资源版本" }}</h4>
            <span class="health-badge" :data-state="v.health">{{
              label(v.health)
            }}</span>
          </div>
          <div class="badge-row">
            <UBadge
              v-if="
                v.attributes?.original_disc ||
                ['ISO', 'BDMV'].includes(v.attributes?.format)
              "
              color="primary"
              variant="subtle"
              >原盘版本</UBadge
            >
            <UBadge
              v-for="[key, val] in attributes(v)"
              :key="key"
              color="neutral"
              variant="subtle"
              >{{ val }}</UBadge
            ><span class="small muted">{{ bytes(v.size) }}</span
            ><span v-if="v.episodes?.length" class="small muted"
              >集数：{{ v.episodes.join("、") }}</span
            >
          </div>
          <p v-if="v.attributes?.evidence" class="attribute-evidence">
            属性依据：{{ v.attributes.evidence }}
          </p>
          <dl class="source-details">
            <div>
              <dt>分享来源</dt>
              <dd>{{ v.source_title || "115 分享" }}</dd>
            </div>
            <div>
              <dt>目录访问</dt>
              <dd>{{ label(v.source_access_status || "uncertain") }}</dd>
            </div>
            <div>
              <dt>访问码</dt>
              <dd>
                <code>{{ v.access_code || "无需访问码" }}</code
                ><button
                  v-if="v.access_code"
                  class="text-button"
                  @click="copy(v.access_code)"
                >
                  复制
                </button>
              </dd>
            </div>
            <div class="full-width">
              <dt>完整相对路径</dt>
              <dd class="path-value">{{ v.path }}</dd>
            </div>
            <div v-if="v.path_corrected" class="full-width">
              <dt>原扫描路径</dt>
              <dd class="path-value">
                {{ v.original_path
                }}<span class="small muted">（展示路径经管理员审核修正）</span>
              </dd>
            </div>
            <div>
              <dt>节点最近检测</dt>
              <dd>{{ date(v.checked_at) }}</dd>
            </div>
            <div v-if="!v.is_demo">
              <dt>分享入口检测</dt>
              <dd>{{ label(v.share_health || 'unchecked') }} · {{ date(v.share_checked_at) }}</dd>
            </div>
            <div v-if="!v.is_demo">
              <dt>{{ v.node_kind === 'directory' ? '目录存在性' : '文件存在性' }}</dt>
              <dd>{{ label(v.node_health || 'unchecked') }}（目录接口记录，非媒体实测）</dd>
            </div>
            <div v-if="!v.is_demo">
              <dt>115 网页打开状态</dt>
              <dd>未验证，目录接口可读不代表网页一定可打开</dd>
            </div>
          </dl>
          <div class="version-actions">
            <UButton
              v-if="!v.is_demo && safeURL(v.share_url)"
              :href="safeURL(v.share_url)"
              target="_blank"
              rel="noopener noreferrer"
              icon="i-lucide-external-link"
              >打开原分享</UButton
            ><UButton
              color="neutral"
              variant="outline"
              icon="i-lucide-copy"
              @click="copy(v.path)"
              >复制完整路径</UButton
            ><UButton
              v-if="!v.is_demo && safeURL(v.share_url)"
              color="neutral"
              variant="ghost"
              @click="
                copy(
                  v.share_url +
                    (v.access_code ? ' 访问码：' + v.access_code : ''),
                )
              "
              >复制分享信息</UButton
            >
          </div>
        </article>
      </section>
    </section></template
  >
</template>
