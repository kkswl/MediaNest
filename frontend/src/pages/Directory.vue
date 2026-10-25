<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api, type Row } from "../api";
const props = defineProps<{ kind: "people" | "collections" }>();
const items = ref<Row[]>([]);
const error = ref("");
const loading = ref(true);
const search = ref("");
function collectionLabel(kind: string) {
  return (
    (
      {
        actor: "演员专题",
        series: "影视系列",
        source: "来源合集",
        directory: "目录合集",
      } as Record<string, string>
    )[kind] || kind
  );
}
const filtered = computed(() =>
  items.value.filter((i) =>
    String(i.name).toLowerCase().includes(search.value.toLowerCase()),
  ),
);
async function load() {
  loading.value = true;
  error.value = "";
  try {
    items.value = (await api("/" + props.kind)).items;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(() => props.kind, load);
</script>
<template>
  <section class="page-heading">
    <p class="eyebrow">
      {{
        kind === "people" ? "PEOPLE BEHIND THE STORIES" : "CURATED CONNECTIONS"
      }}
    </p>
    <h1>
      {{ kind === "people" ? "循着演员，发现作品。" : "好作品，自成一集。" }}
    </h1>
    <p class="lead">
      {{
        kind === "people"
          ? "从已确认的作品资料中，找到熟悉的名字。"
          : "影视系列、演员专题与来源目录合集，分别归类，不混为一谈。"
      }}
    </p>
  </section>
  <label class="directory-search"
    >{{ kind === "people" ? "查找演员" : "查找合集"
    }}<input v-model="search" type="search" placeholder="输入名称筛选"
  /></label>
  <div v-if="error" class="state-panel" role="alert">
    <p>{{ error }}</p>
    <UButton @click="load">重试</UButton>
  </div>
  <p v-else-if="loading" role="status">正在加载目录…</p>
  <div v-else-if="!filtered.length" class="state-panel">
    <UIcon name="i-lucide-library" />
    <h3>暂无匹配条目</h3>
    <p>作品识别并关联后，这里会自动更新。</p>
  </div>
  <div v-else class="directory-grid">
    <RouterLink
      v-for="(item, i) in filtered"
      :key="item.id"
      :to="{
        path: '/',
        query: { [kind === 'people' ? 'person' : 'collection']: item.id },
      }"
      class="directory-card"
      ><span class="directory-avatar"
        ><UIcon
          :name="
            kind === 'people' ? 'i-lucide-user-round' : 'i-lucide-folders'
          " /></span
      ><span class="directory-number">{{
        String(i + 1).padStart(2, "0")
      }}</span>
      <h2>{{ item.name }}</h2>
      <p>
        {{ item.count ?? item.work_count ?? 0 }} 部作品
        <span v-if="item.kind">· {{ collectionLabel(item.kind) }}</span>
      </p>
      <UIcon name="i-lucide-arrow-up-right" class="directory-arrow"
    /></RouterLink>
  </div>
</template>
