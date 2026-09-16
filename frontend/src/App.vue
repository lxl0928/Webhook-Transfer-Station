<script setup lang="ts">
import BusinessIcon from "./components/BusinessIcon.vue";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Connection,
  Document,
  Setting,
  SwitchButton,
  ArrowRight,
} from "@element-plus/icons-vue";
import { api } from "./api";

import ChatAssistant from "./components/ChatAssistant.vue";
const refreshKey = ref(0);
const route = useRoute();
const router = useRouter();
const titles: Record<string, string> = {
  "/webhooks": "中转规则",
  "/logs": "消息日志",
  "/profile": "个人设置",
  "/skills": "Skill 管理",
};
const title = computed(() => titles[route.path] ?? "工作台");
async function logout() {
  try {
    await api.post("/api/auth/logout");
  } catch {
    /* Interceptor displays the error. */
  }
  sessionStorage.removeItem("station-token");
  await router.push("/login");
}
</script>

<template>
  <router-view v-if="route.path === '/login'" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <router-link to="/" class="brand">
        <span class="brand-mark"><el-icon><Connection /></el-icon></span><span>中转站<small>WEBHOOK STATION</small></span>
      </router-link>
      <div class="nav-caption">工作空间</div>
      <nav aria-label="主导航">
        <router-link to="/webhooks">
          <el-icon><Connection /></el-icon>中转规则
        </router-link>
        <router-link to="/logs">
          <el-icon><Document /></el-icon>消息日志
        </router-link>
        <router-link to="/skills"><BusinessIcon kind="feature" value="ai" />Skill 管理</router-link>
        <router-link to="/profile">
          <el-icon><Setting /></el-icon>个人设置
        </router-link>
      </nav>
      <div class="sidebar-note">
        让每个重要事件<br /><span>成为有价值的消息。</span><small class="source-caption">Gitee · 夜莺 · 自定义服务</small>
      </div>
      <a class="docs-link" href="/docs" target="_blank" rel="noopener">API 文档 ↗</a>
      <button class="logout" @click="logout">
        <el-icon><SwitchButton /></el-icon>退出登录
      </button>
    </aside>
    <main class="main-area">
      <header class="topbar">
        <span>工作空间 <el-icon><ArrowRight /></el-icon>
          <strong>{{ title }}</strong></span><span class="admin-badge">A <span>管理员</span><el-button class="mobile-logout" link @click="logout">退出</el-button></span>
      </header>
      <div class="page-content"><router-view :key="refreshKey" /></div>
      <footer>Webhook Station <span>Gitee · 夜莺 · 自定义服务 → 团队消息</span></footer>
    </main>
    <ChatAssistant @changed="refreshKey++" />
  </div>
</template>
