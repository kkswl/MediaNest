<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { posterOf, safeURL, type Row } from "../api";
const props = defineProps<{ work: Row }>();
const failed = ref(false);
const fallbackFailed = ref(false);
const primary = computed(() => posterOf(props.work));
const fallback = computed(() =>
  safeURL(props.work.info?.fallback_poster || props.work.info?.tmdb_poster),
);
const url = computed(() =>
  !failed.value ? primary.value : !fallbackFailed.value ? fallback.value : "",
);
watch(
  () => props.work,
  () => {
    failed.value = false;
    fallbackFailed.value = false;
  },
);
const hue = computed(
  () =>
    (Array.from(String(props.work.title)).reduce(
      (n, c) => n + c.charCodeAt(0),
      0,
    ) %
      180) +
    120,
);
function fail() {
  if (!failed.value) failed.value = true;
  else fallbackFailed.value = true;
}
</script>
<template>
  <div class="poster" :style="{ '--poster-hue': hue }">
    <img
      v-if="url"
      :src="url"
      :alt="`${work.title}海报`"
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="fail"
    />
    <div v-else class="poster-placeholder">
      <div class="poster-orbit" />
      <span class="poster-eyebrow">YINGJI / ARCHIVE</span
      ><UIcon name="i-lucide-film" class="poster-symbol" /><strong>{{
        work.title
      }}</strong
      ><span class="poster-year"
        >{{ work.year || "年份待完善" }} · 目录封面</span
      >
    </div>
    <slot />
  </div>
</template>
