<script setup lang="ts">
import Poster from "./Poster.vue";
import { category, type Row } from "../api";
defineProps<{ work: Row }>();
</script>
<template>
  <RouterLink :to="`/works/${work.id}`" class="work-card"
    ><Poster :work="work"
      ><span class="poster-category">{{ category(work.category) }}</span
      ><span v-if="work.status !== 'confirmed'" class="poster-incomplete"
        >信息待完善</span
      ></Poster
    >
    <div class="work-card-info">
      <h3>{{ work.title }}</h3>
      <p>
        <span>{{ work.year || "年份待完善" }}</span
        ><span
          >{{ work.variant_count || 0 }} 个版本
          <UIcon name="i-lucide-arrow-up-right"
        /></span>
      </p></div
  ></RouterLink>
</template>
