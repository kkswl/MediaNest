<script setup lang="ts">
import { onMounted } from "vue";
import { feedback, loadMe, session } from "./api";
onMounted(loadMe);
</script>
<template>
  <UApp
    ><a href="#main" class="skip-link">跳到主要内容</a>
    <header class="site-header">
      <div class="shell header-inner">
        <RouterLink to="/" class="brand" aria-label="映集首页"
          ><span class="brand-mark"><UIcon name="i-lucide-clapperboard" /></span
          ><span>映集<small>YINGJI · INDEX</small></span></RouterLink
        >
        <nav aria-label="主导航">
          <RouterLink to="/" :class="{ 'nav-active': $route.path === '/' }"
            >发现</RouterLink
          ><RouterLink to="/people">演员</RouterLink
          ><RouterLink to="/collections">合集</RouterLink
          ><RouterLink to="/admin" class="admin-link"
            ><UIcon name="i-lucide-sliders-horizontal" />{{
              session.user ? "管理控制台" : "后台管理"
            }}</RouterLink
          >
        </nav>
      </div>
    </header>
    <main id="main" class="shell main-shell"><RouterView /></main>
    <footer class="site-footer shell">
      <span>映集 / 留住目录，发现好内容。</span
      ><span>只做索引 · 不转存 · 不播放</span>
    </footer>
    <div
      v-if="feedback.message"
      class="toast"
      :class="{ 'toast-error': feedback.error }"
      role="status"
      aria-live="polite"
    >
      <UIcon
        :name="
          feedback.error ? 'i-lucide-circle-alert' : 'i-lucide-circle-check'
        "
      />{{ feedback.message }}
    </div></UApp
  >
</template>
