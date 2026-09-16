<script setup lang="ts">
import BusinessIcon from "./BusinessIcon.vue";
import { computed, nextTick, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessageBox } from "element-plus";
import { api } from "../api";
const emit = defineEmits<{ changed: [] }>();
const router = useRouter();
interface Message {
  id: string;
  role: string;
  content: string;
  trace_id: string;
  tool_calls?: { function: { name: string } }[];
}
interface Action {
  id: string;
  tool_name: string;
  arguments: unknown;
  status: string;
  secret_fields: string[];
  result: unknown;
  expires_at: string;
}
interface Detail {
  id: string;
  messages: Message[];
  actions: Action[];
}
const open = ref(false),
  busy = ref(false),
  input = ref(""),
  cid = ref(""),
  skill = ref("");
const sessions = ref<{ id: string; title: string }[]>([]),
  skills = ref<{ id: string; name: string; enabled: boolean }[]>([]);
const detail = ref<Detail>({ id: "", messages: [], actions: [] }),
  scroll = ref<HTMLElement>();
const secrets = ref<Record<string, Record<string, string>>>({});
const labels: Record<string, string> = {
  source_secret: "源站校验密钥（新增必填）",
  target_url: "群机器人 Webhook URL（新增必填）",
  target_secret: "机器人签名密钥（选填）",
  llm_api_key: "LLM API Key（留空保留）",
  current_password: "当前密码",
  new_password: "新密码（至少 10 字符）",
};
const clock = ref(Date.now());
const timer = window.setInterval(() => { clock.value = Date.now(); }, 1000);
onUnmounted(() => window.clearInterval(timer));
const pending = computed(() =>
  detail.value.actions.some(
    (a) => a.status === "pending" && Date.parse(a.expires_at) > clock.value,
  ),
);
async function bottom() {
  await nextTick();
  scroll.value?.scrollTo({
    top: scroll.value.scrollHeight,
    behavior: "smooth",
  });
}
async function list() {
  sessions.value = (await api.get("/api/chat/conversations")).data.items;
}
async function show() {
  open.value = !open.value;
  if (!open.value) return;
  skills.value = (await api.get("/api/skills")).data.items;
  await list();
  if (!cid.value && sessions.value.length) cid.value = sessions.value[0]!.id;
  if (cid.value) await load();
}
async function load() {
  detail.value = (await api.get(`/api/chat/conversations/${cid.value}`)).data;
  secrets.value = Object.fromEntries(
    detail.value.actions.map((a) => [a.id, {}]),
  );
  await bottom();
}
async function fresh() {
  cid.value = "";
  detail.value = { id: "", messages: [], actions: [] };
  secrets.value = {};
}
async function send() {
  if (!input.value.trim() || busy.value || pending.value) return;
  busy.value = true;
  const text = input.value.trim();
  try {
    if (!cid.value)
      cid.value = (await api.post("/api/chat/conversations")).data.id;
    input.value = "";
    detail.value.messages.push({
      id: "sending",
      role: "user",
      content: text,
      trace_id: "",
    });
    await bottom();
    detail.value = (
      await api.post(`/api/chat/conversations/${cid.value}/messages`, {
        content: text,
        skill_id: skill.value || null,
      })
    ).data;
    secrets.value = Object.fromEntries(
      detail.value.actions.map((a) => [a.id, {}]),
    );
    await list();
  } catch {
    input.value = text;
    if (cid.value) await load();
  } finally {
    busy.value = false;
    await bottom();
  }
}
async function decide(action: Action, decision: "approve" | "reject") {
  busy.value = true;
  try {
    const fields = Object.fromEntries(
      Object.entries(secrets.value[action.id] || {}).filter(([, v]) => v),
    );
    const result = (
      await api.post(
        `/api/chat/conversations/${cid.value}/actions/${action.id}/decision`,
        { decision, secrets: decision === "approve" ? fields : {} },
      )
    ).data;
    secrets.value[action.id] = {};
    if (
      action.tool_name === "change_user_password" &&
      result.status === "succeeded"
    ) {
      sessionStorage.removeItem("station-token");
      await router.push("/login");
      return;
    }
    await load();
    emit("changed");
    skills.value = (await api.get("/api/skills")).data.items;
  } finally {
    busy.value = false;
  }
}
async function remove() {
  if (!cid.value) return;
  try {
    await ElMessageBox.confirm(
      "删除本对话及其操作记录？已执行的数据修改不会撤销。",
      "删除对话",
    );
  } catch {
    return;
  }
  await api.delete(`/api/chat/conversations/${cid.value}`);
  await fresh();
  await list();
}
</script>
<template>
  <button
    class="assistant-fab"
    :aria-expanded="open"
    aria-label="打开智能助手"
    @click="show"
  >
    {{ open ? "×" : "✦" }}<span v-if="!open">智能助手</span>
  </button>
  <section v-if="open" class="assistant-panel" aria-label="智能助手对话">
    <header>
      <div><strong>中转站助手</strong><small>使用个人设置中的 LLM</small></div>
      <el-button link :disabled="busy" @click="fresh">新对话</el-button><el-button link :disabled="busy || !cid" @click="remove">删除</el-button><el-button link aria-label="关闭聊天" @click="open = false">
        关闭
      </el-button>
    </header>
    <div class="assistant-selects">
      <el-select
        v-model="cid"
        placeholder="历史对话"
        :disabled="busy"
        @change="load"
      >
        <el-option
          v-for="s in sessions"
          :key="s.id"
          :value="s.id"
          :label="s.title"
        />
      </el-select><el-select v-model="skill" placeholder="自动选择 Skill" :disabled="busy">
        <el-option label="自动选择 Skill" value="" /><el-option
          v-for="s in skills.filter((s) => s.enabled)"
          :key="s.id"
          :value="s.id"
          :label="s.name"
        />
      </el-select>
    </div>
    <div ref="scroll" class="assistant-messages" aria-live="polite">
      <div v-if="!detail.messages.length" class="assistant-welcome">
        <h3>用对话管理中转站</h3>
        <p>查询日志、创建规则，或调整你的 Skill。</p>
        <button
          v-for="example in [
            '查看我的中转规则',
            '查询最近失败的消息',
            '创建一个夜莺到飞书的中转规则',
          ]"
          :key="example"
          @click="input = example"
        >
          {{ example }} ↗
        </button>
      </div>
      <article
        v-for="m in detail.messages"
        :key="m.id"
        :class="['chat-message', m.role]"
      >
        <template v-if="m.role === 'tool'">
          <details>
            <summary><BusinessIcon kind="tool" value="read" />工具结果</summary>
            <pre>{{ m.content }}</pre>
          </details>
        </template>
        <template v-else>
          <small>{{ m.role === "user" ? "你" : "助手" }}</small>
          <p v-if="m.content">{{ m.content }}</p>
          <small v-for="(call, i) in m.tool_calls" :key="i">调用 {{ call.function.name }}</small><small v-if="m.trace_id" class="trace">Trace: {{ m.trace_id }}</small>
        </template>
      </article>
      <article v-for="a in detail.actions" :key="a.id" class="chat-action">
        <strong>{{ a.tool_name }}</strong><el-tag size="small"><BusinessIcon kind="status" :value="a.status === 'pending' && Date.parse(a.expires_at) <= clock ? 'expired' : a.status" />{{ ({pending:"待确认",succeeded:"已完成",rejected:"已取消",expired:"已过期"} as Record<string,string>)[a.status === "pending" && Date.parse(a.expires_at) <= clock ? "expired" : a.status] || a.status }}</el-tag>
        <pre>{{ JSON.stringify(a.arguments, null, 2) }}</pre>
        <template
          v-if="a.status === 'pending' && Date.parse(a.expires_at) > clock"
        >
          <p>确认后执行；15 分钟内有效。重试消息可能重复通知。</p>
          <el-form label-position="top">
            <el-form-item
              v-for="field in a.secret_fields"
              :key="field"
              :label="labels[field] || field"
            >
              <el-input
                :model-value="secrets[a.id]?.[field] || ''"
                type="password"
                show-password
                autocomplete="off"
                @update:model-value="
                  (value: string) => {
                    (secrets[a.id] ||= {})[field] = value;
                  }
                "
              />
            </el-form-item>
          </el-form><el-button
            type="primary"
            :disabled="busy"
            @click="decide(a, 'approve')"
          >
            确认执行
          </el-button><el-button :disabled="busy" @click="decide(a, 'reject')">
            取消操作
          </el-button>
        </template>
        <details v-else-if="a.result">
          <summary>执行结果</summary>
          <pre>{{ JSON.stringify(a.result, null, 2) }}</pre>
        </details>
      </article>
      <p v-if="busy" class="thinking"><BusinessIcon kind="status" value="processing" />助手正在处理，请稍候…</p>
    </div>
    <form class="assistant-composer" @submit.prevent="send">
      <small>请勿在聊天中输入密码或密钥；通过操作确认表单填写。</small><el-input
        v-model="input"
        type="textarea"
        :rows="2"
        maxlength="4000"
        placeholder="描述你想完成的操作…"
        :disabled="busy || pending"
        @keydown.ctrl.enter.prevent="send"
      />
      <div>
        <span>{{
          pending ? "请先确认或取消待执行操作" : "Ctrl + Enter 发送"
        }}</span><el-button
          native-type="submit"
          type="primary"
          :loading="busy"
          :disabled="pending || !input.trim()"
        >
          发送
        </el-button>
      </div>
    </form>
  </section>
</template>
<style scoped>
.assistant-fab {
  position: fixed;
  right: 28px;
  bottom: 24px;
  background: #387b68;
  color: white;
  border: 0;
  border-radius: 30px;
  padding: 15px 21px;
  box-shadow: 0 8px 28px #173d7950;
  z-index: 2100;
  cursor: pointer;
  font-size: 20px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.assistant-fab span {
  font-size: 14px;
}
.assistant-panel {
  position: fixed;
  right: 28px;
  bottom: 88px;
  width: 460px;
  height: min(760px, calc(100dvh - 110px));
  background: #fff;
  border: 1px solid #dce4ef;
  border-radius: 18px;
  box-shadow: 0 15px 70px #20395b30;
  z-index: 2100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.assistant-panel header {
  display: flex;
  align-items: center;
  padding: 18px;
  gap: 8px;
  border-bottom: 1px solid #edf0f5;
}
.assistant-panel header div {
  flex: 1;
}
.assistant-panel header small {
  display: block;
  color: #64748b;
  margin-top: 5px;
}
.assistant-selects {
  display: flex;
  gap: 8px;
  padding: 12px;
}
.assistant-selects > * {
  width: 50%;
}
.assistant-messages {
  flex: 1;
  overflow: auto;
  padding: 16px;
  background: #f7f9fc;
  min-height: 0;
}
.assistant-welcome {
  padding: 10px;
  color: #334155;
}
.assistant-welcome button {
  display: block;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin-top: 10px;
  text-align: left;
  cursor: pointer;
  width: 100%;
}
.chat-message {
  padding: 12px;
  margin-bottom: 12px;
  background: white;
  border: 1px solid #e5eaf1;
  border-radius: 12px;
  overflow-wrap: anywhere;
}
.chat-message.user {
  background: #edf3ff;
  margin-left: 30px;
}
.chat-message p {
  white-space: pre-wrap;
  line-height: 1.7;
  margin: 7px 0;
}
.chat-message small {
  display: block;
  color: #64748b;
}
.chat-message .trace {
  font-size: 10px;
  opacity: 0.7;
}
.chat-message.tool {
  font-size: 12px;
}
.assistant-panel pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
  max-height: 240px;
  overflow: auto;
}
.chat-action {
  border: 1px solid #b7ccf7;
  border-radius: 12px;
  background: white;
  padding: 14px;
  margin-bottom: 12px;
  overflow-wrap: anywhere;
}
.chat-action strong {
  display: block;
  margin-bottom: 8px;
}
.chat-action p {
  font-size: 12px;
  color: #64748b;
}
.assistant-composer {
  padding: 14px;
  border-top: 1px solid #e5eaf1;
}
.assistant-composer > small {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 9px;
}
.assistant-composer > div:last-child {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  font-size: 11px;
  color: #64748b;
}
.thinking {
  font-size: 13px;
  color: #2563eb;
}
@media (max-width: 600px) {
  .assistant-panel {
    right: 8px;
    left: 8px;
    width: auto;
    bottom: 78px;
    height: calc(100dvh - 90px);
  }
  .assistant-fab {
    right: 14px;
    bottom: 15px;
  }
}
</style>
