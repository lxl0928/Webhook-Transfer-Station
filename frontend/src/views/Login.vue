<script setup lang="ts">
import BusinessIcon from "../components/BusinessIcon.vue";
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Connection, ArrowRight } from "@element-plus/icons-vue";
import { api } from "../api";

const router = useRouter();
const form = reactive({ username: "admin", password: "" });
const busy = ref(false);
async function submit() {
  if (!form.username || !form.password) return;
  busy.value = true;
  try {
    const { data } = await api.post("/api/auth/login", form);
    sessionStorage.setItem("station-token", data.access_token);
    await router.push("/webhooks");
  } catch {
    /* Error is displayed by the shared interceptor. */
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-story">
      <div class="brand">
        <span class="brand-mark"><el-icon><Connection /></el-icon></span><span>中转站<small>WEBHOOK STATION</small></span>
      </div>
      <div class="story-main">
        <div class="eyebrow">CONNECT. UNDERSTAND. DELIVER.</div>
        <h1>每个重要事件，<br />团队都能心中有数。</h1>
        <p>
          连接 Gitee、夜莺与自定义服务，让 AI 整理事件，<br />将重要信息送到对的人面前。
        </p>
        <div class="pipeline">
          <span><BusinessIcon kind="source" value="generic" />多源回调<small>Gitee · 夜莺 · 自定义服务</small></span><el-icon><ArrowRight /></el-icon><span class="pipeline-ai"><BusinessIcon kind="feature" value="ai" />LLM<small>理解与整理</small></span><el-icon><ArrowRight /></el-icon><span><BusinessIcon kind="target" value="wecom" />团队群聊<small>即时触达</small></span>
        </div>
      </div>
      <div class="story-footer">为更清晰的协作而构建。</div>
    </section>
    <section class="login-form">
      <div>
        <div class="eyebrow">WELCOME BACK</div>
        <h2>登录工作空间</h2>
        <p class="muted">管理你的 Webhook 消息中转。</p>
        <el-form label-position="top" size="large" @submit.prevent="submit">
          <el-form-item label="用户名">
            <el-input
              v-model="form.username"
              autocomplete="username"
              placeholder="请输入用户名"
            />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              autocomplete="current-password"
              placeholder="请输入密码"
            />
          </el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="busy"
            class="full-width"
          >
            登录 <el-icon><ArrowRight /></el-icon>
          </el-button>
        </el-form>
        <p class="login-note">仅供已授权管理员访问</p>
      </div>
    </section>
  </div>
</template>
