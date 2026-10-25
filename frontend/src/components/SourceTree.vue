<script setup lang="ts">
import { ref } from "vue";
import { api, bytes, label, type Row } from "../api";
const props = defineProps<{
  sourceId: number | string;
  parent?: string | number;
  depth?: number;
  id?: string;
}>();
const emit = defineEmits<{ index: [node: Row] }>();
const nodes = ref<Row[]>([]);
const loading = ref(false);
const error = ref("");
const loaded = ref(false);
const expanded = ref<Record<string, boolean>>({});
const page = ref(1);
const total = ref(0);
async function load(more = false) {
  loading.value = true;
  error.value = "";
  const next = more ? page.value + 1 : 1;
  try {
    const data = await api(
      `/admin/sources/${props.sourceId}/nodes?parent=${encodeURIComponent(props.parent ?? "0")}&page=${next}`,
    );
    nodes.value = more ? [...nodes.value, ...data.items] : data.items;
    total.value = data.total ?? nodes.value.length;
    page.value = next;
    loaded.value = true;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
load();
</script>
<template>
  <ul :id="id" class="source-tree" :aria-label="depth ? '子目录' : '分享目录'">
    <li v-if="loading && !loaded" role="status">正在读取目录…</li>
    <li v-else-if="error" role="alert">
      {{ error }}
      <UButton color="neutral" variant="ghost" @click="load()">重试</UButton>
    </li>
    <li v-else-if="loaded && !nodes.length" class="muted">
      此层暂无缓存节点；浏览目录不会自动扫描。
    </li>
    <li v-for="node in nodes" :key="node.id">
      <div class="tree-row">
        <button
          v-if="node.is_dir"
          class="tree-node"
          :aria-expanded="!!expanded[node.id]"
          :aria-controls="`source-tree-${node.id}`"
          @click="expanded[node.id] = !expanded[node.id]"
        >
          <UIcon
            :name="
              expanded[node.id] ? 'i-lucide-folder-open' : 'i-lucide-folder'
            "
          /><span>{{ node.name }}</span
          ><UIcon
            :name="
              expanded[node.id]
                ? 'i-lucide-chevron-down'
                : 'i-lucide-chevron-right'
            "
          /></button
        ><span v-else class="tree-node"
          ><UIcon name="i-lucide-file" /><span>{{ node.name }}</span></span
        ><span class="tree-meta"
          >{{ !node.is_dir ? bytes(node.size) : "" }} ·
          {{ label(node.health) }}</span
        >
        <UButton v-if="node.is_dir" color="neutral" variant="outline" class="min-h-11"
          :aria-label="`索引此目录：${node.path}`" @click="emit('index', node)">索引此目录</UButton>
      </div>
      <p class="tree-path">{{ node.path }}</p>
      <SourceTree
        v-if="node.is_dir && expanded[node.id]"
        :id="`source-tree-${node.id}`"
        :source-id="sourceId"
        :parent="node.remote_id"
        :depth="(depth || 0) + 1"
        @index="emit('index', $event)"
      />
    </li>
    <li v-if="nodes.length < total">
      <UButton
        color="neutral"
        variant="outline"
        :loading="loading"
        @click="load(true)"
        >加载更多（{{ nodes.length }} / {{ total }}）</UButton
      >
    </li>
  </ul>
</template>
