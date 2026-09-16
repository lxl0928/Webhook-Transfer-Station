<script setup lang="ts">
import BusinessIcon from "../components/BusinessIcon.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Plus,
  Search,
  ArrowRight,
  Refresh,
  CopyDocument,
} from "@element-plus/icons-vue";
import {
  api,
  copy,
  events,
  formatDate,
  targets,
  sources,
  type Hook,
} from "../api";

const router = useRouter();
const items = ref<Hook[]>([]);
const total = ref(0);
const page = ref(1);
const query = ref("");
const busy = ref(false);
const saving = ref(false);
const dialog = ref(false);
const editing = ref<string | null>(null);
const sourceInfo = ref("{}");
const sourceSecretSet = ref(false);
const defaults = () => ({
  name: "",
  source_type: "generic" as Hook["source_type"],
  source_auth_enabled: true,
  source_auth: "header" as Hook["source_auth"],
  source_token_header: "X-Webhook-Token",
  target_mentions: {
    all: false,
    user_ids: [] as string[],
    mobiles: [] as string[],
  },
  source_url: "",
  source_secret: "",
  events: [] as string[],
  source_template: "{{payload}}",
  llm_enabled: true,
  llm_prompt:
    "请用中文概括以下回调事件，保留来源、关键内容、严重程度和相关链接。不要推测未提供的信息，控制在 500 字以内。",
  target_type: "feishu" as Hook["target_type"],
  target_url: "",
  target_secret: "",
  target_template: "[{{source_name}}] {{event}}\n{{llm_output}}",
  enabled: true,
});
const form = reactive(defaults());
const customEvents = ref("");
const splitValues = (value: string) => [
  ...new Set(value.split(/[,，\s]+/).filter(Boolean)),
];
const mentionIds = computed({
  get: () => form.target_mentions.user_ids.join("\n"),
  set: (value: string) => {
    form.target_mentions.user_ids = splitValues(value);
  },
});
const mentionMobiles = computed({
  get: () => form.target_mentions.mobiles.join("\n"),
  set: (value: string) => {
    form.target_mentions.mobiles = splitValues(value);
  },
});
const giteeEvents = Object.fromEntries(
  ["push", "pull_request", "tag", "comment"].map((key) => [key, events[key]]),
);
function changeSource() {
  form.events = form.source_type === "gitee" ? Object.keys(giteeEvents) : [];
  customEvents.value = "";
  form.source_auth = "header";
}
function changeTarget() {
  form.target_mentions = { all: false, user_ids: [], mobiles: [] };
  form.target_url = "";
  form.target_secret = "";
}

async function load() {
  busy.value = true;
  try {
    const { data } = await api.get("/api/webhooks", {
      params: { page: page.value, q: query.value },
    });
    items.value = data.items;
    total.value = data.total;
  } catch {
    /* Shared error handler. */
  } finally {
    busy.value = false;
  }
}
function open(hook?: Hook) {
  editing.value = hook?.wid ?? null;
  sourceSecretSet.value = hook?.source_secret_set ?? false;
  Object.assign(form, defaults());
  if (hook) {
    for (const key of Object.keys(defaults()) as (keyof typeof form)[]) {
      if (key in hook) Object.assign(form, { [key]: hook[key as keyof Hook] });
    }
    form.events = [...hook.events];
    form.target_mentions = {
      ...hook.target_mentions,
      user_ids: [...hook.target_mentions.user_ids],
      mobiles: [...hook.target_mentions.mobiles],
    };
  }
  customEvents.value = form.events.join(", ");
  sourceInfo.value = JSON.stringify(hook?.source_info ?? {}, null, 2);
  dialog.value = true;
}
async function save() {
  if (
    !form.name.trim() ||
    (form.source_type === "gitee" &&
      (!form.source_url || !form.events.length)) ||
    (!editing.value && !form.target_url) ||
    (form.source_auth_enabled && (!sourceSecretSet.value || form.source_secret) && form.source_secret.length < 8)
  ) {
    ElMessage.warning(
      form.source_type === "gitee"
        ? "请填写名称、仓库地址、接收事件及目标 URL；开启回调鉴权时需至少 8 位密钥"
        : "请填写名称及目标 URL；开启回调鉴权时需至少 8 位密钥",
    );
    return;
  }
  let source_info: unknown;
  try {
    source_info = JSON.parse(sourceInfo.value);
    if (
      source_info === null ||
      Array.isArray(source_info) ||
      typeof source_info !== "object"
    )
      throw Error();
  } catch {
    ElMessage.warning("源站附加信息必须为 JSON 对象");
    return;
  }
  const body: Record<string, unknown> = {
    ...form,
    source_info,
    events:
      form.source_type === "gitee"
        ? form.events
        : splitValues(customEvents.value),
    target_mentions: form.target_mentions.all
      ? { all: true, user_ids: [], mobiles: [] }
      : form.target_mentions,
  };
  if (!form.source_auth_enabled) delete body.source_secret;
  if (editing.value) {
    if (!form.source_secret) delete body.source_secret;
    if (!form.target_url) delete body.target_url;
    if (!form.target_secret) delete body.target_secret;
  }
  saving.value = true;
  try {
    if (editing.value) await api.put(`/api/webhooks/${editing.value}`, body);
    else await api.post("/api/webhooks", body);
    ElMessage.success(
      editing.value
        ? "规则已更新"
        : "规则已创建，复制回调 URL 到源站并配置鉴权即可",
    );
    dialog.value = false;
    await load();
  } catch {
    /* Shared error handler. */
  } finally {
    saving.value = false;
  }
}
async function remove(hook: Hook) {
  try {
    await ElMessageBox.confirm(
      `删除“${hook.name}”后将不再接收新回调。已有队列任务会继续处理，历史日志会保留。`,
      "删除中转规则",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    await api.delete(`/api/webhooks/${hook.wid}`);
    ElMessage.success("已删除");
    if (items.value.length === 1 && page.value > 1) page.value--;
    await load();
  } catch {
    /* Shared error handler. */
  }
}
function search() {
  page.value = 1;
  void load();
}
onMounted(load);
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <div class="eyebrow">YOUR CONNECTIONS</div>
        <h1>
          中转规则 <span class="count-pill">{{ total }}</span>
        </h1>
        <p>连接 Gitee · 夜莺 · 自定义服务，整理回调并通知相关人员。</p>
      </div>
      <el-button type="primary" :icon="Plus" size="large" @click="open()">
        新增中转
      </el-button>
    </div>
    <div class="flow-banner">
      <span class="flow-step"><span class="step-number">01</span><b>多源回调</b><small>Gitee · 夜莺 · 自定义服务</small></span><el-icon><ArrowRight /></el-icon><span class="flow-step"><span class="step-number">02</span><b>AI 理解与编排</b><small>你的提示词与消息模板</small></span><el-icon><ArrowRight /></el-icon><span class="flow-step"><span class="step-number">03</span><b>团队群机器人</b><small>飞书 · 企业微信 · 钉钉</small></span>
    </div>
    <div class="panel">
      <div class="panel-toolbar">
        <h3>全部中转规则</h3>
        <div class="toolbar-actions">
          <el-input
            v-model="query"
            placeholder="搜索规则名称"
            :prefix-icon="Search"
            clearable
            @keyup.enter="search"
            @clear="search"
          /><el-button :icon="Refresh" aria-label="刷新规则" @click="load" />
        </div>
      </div>
      <div v-loading="busy" class="hook-list">
        <el-empty
          v-if="!items.length && !busy"
          description="还没有中转规则，从连接第一个服务开始"
        >
          <el-button type="primary" @click="open()"> 新增中转 </el-button>
        </el-empty>
        <article v-for="hook in items" :key="hook.wid" class="hook-row">
          <div class="hook-icon">
            <BusinessIcon kind="source" :value="hook.source_type" />
          </div>
          <div class="hook-main">
            <div class="hook-title">
              <h3>{{ hook.name }}</h3>
              <el-tag
                :type="hook.enabled ? 'success' : 'danger'"
                effect="plain"
                size="small"
              >
                <BusinessIcon kind="status" :value="hook.enabled ? 'enabled' : 'disabled'" />{{ hook.enabled ? "已启用" : "已停用" }}
              </el-tag><span v-if="hook.llm_enabled" class="ai-tag"><BusinessIcon kind="feature" value="ai" />AI 处理</span><span v-else class="ai-tag"><BusinessIcon kind="feature" value="template" />模板直转</span>
            </div>
            <p class="repo-url">
              {{ sources[hook.source_type] }} ·
              {{ hook.source_url || "自定义事件入口" }}
            </p>
            <div class="event-tags">
              <span><BusinessIcon kind="auth" :value="hook.source_auth_enabled ? 'bearer' : 'none'" />{{ hook.source_auth_enabled ? '回调鉴权已开启' : '回调鉴权已关闭' }}</span>
              <span v-if="!hook.events.length"><BusinessIcon kind="event" value="webhook" />全部事件</span>
              <span v-if="hook.target_mentions.all"><BusinessIcon kind="feature" value="all" />@所有人</span>
              <span
                v-else-if="
                  hook.target_mentions.user_ids.length +
                    hook.target_mentions.mobiles.length
                "
              ><BusinessIcon kind="feature" value="member" />@指定成员</span>
              <span v-for="event in hook.events" :key="event"><BusinessIcon kind="event" :value="event" />{{
                events[event] ?? event
              }}</span>
            </div>
            <div class="callback-url">
              <code>{{ hook.url }}</code><el-button
                link
                :icon="CopyDocument"
                aria-label="复制回调 URL"
                @click="copy(hook.url)"
              />
            </div>
          </div>
          <div class="hook-target">
            <small>发送到</small><b><BusinessIcon kind="target" :value="hook.target_type" />{{ targets[hook.target_type] }}</b><span>{{ formatDate(hook.updated_at) }}</span>
          </div>
          <div class="row-actions">
            <el-button link type="primary" @click="open(hook)">编辑</el-button><el-button
              link
              @click="router.push({ path: '/logs', query: { wid: hook.wid } })"
            >
              日志
            </el-button><el-button link type="danger" @click="remove(hook)">
              删除
            </el-button>
          </div>
        </article>
      </div>
      <el-pagination
        v-if="total > 20"
        v-model:current-page="page"
        :total="total"
        :page-size="20"
        layout="prev, pager, next, total"
        @current-change="load"
      />
    </div>
    <p class="page-hint">
      配置提示：根据源站类型设置回调 URL 和鉴权，按需启用 LLM 处理。@
      人员在目标群机器人配置中管理。
    </p>
    <el-drawer
      v-model="dialog"
      :title="editing ? '编辑中转规则' : '创建中转规则'"
      size="min(720px, 100%)"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form label-position="top" class="rule-form" @submit.prevent="save">
        <h3 class="form-section"><span>01</span> 基本信息与源站</h3>
        <el-form-item label="规则名称" required>
          <el-input
            v-model="form.name"
            maxlength="100"
            placeholder="例如：服务异常告警 → 运维群"
          />
        </el-form-item>
        <el-form-item label="源站类型">
          <el-select v-model="form.source_type" @change="changeSource">
            <template #prefix><BusinessIcon kind="source" :value="form.source_type" /></template>
            <el-option
              v-for="(label, value) in sources"
              :key="value"
              :label="label"
              :value="value"
            >
              <BusinessIcon kind="source" :value="value" />{{ label }}
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item
          :label="
            form.source_type === 'gitee'
              ? 'Gitee 仓库页面地址'
              : '源站地址（选填，仅作信息展示）'
          "
          :required="form.source_type === 'gitee'"
        >
          <el-input
            v-model="form.source_url"
            :placeholder="
              form.source_type === 'gitee'
                ? 'https://gitee.com/team/repository'
                : 'https://monitor.example.com'
            "
          />
          <div class="field-help">
            {{
              form.source_type === "gitee"
                ? "校验回调中的仓库地址与此处一致。"
                : "用于标识告警或业务服务来源，仅作展示，不会请求此地址。"
            }}
          </div>
        </el-form-item>
        <el-form-item label="源站回调鉴权">
          <el-switch v-model="form.source_auth_enabled" active-text="开启" inactive-text="关闭" />
          <div class="field-help">仅控制源站到中转站的密钥校验，不影响目标群机器人签名。</div>
        </el-form-item>
        <el-alert v-if="!form.source_auth_enabled" type="warning" show-icon :closable="false" title="关闭后不校验回调密钥，任何持有此回调 URL 的人均可触发消息。规则启停、事件和消息格式校验仍然生效。" />
        <el-form-item v-if="form.source_auth_enabled && form.source_type !== 'gitee'" label="回调鉴权方式">
          <el-select v-model="form.source_auth">
            <template #prefix><BusinessIcon kind="auth" :value="form.source_auth" /></template>
            <el-option label="请求头密钥" value="header"><BusinessIcon kind="auth" value="header" />请求头密钥</el-option>
            <el-option label="Authorization: Bearer Token" value="bearer"><BusinessIcon kind="auth" value="bearer" />Authorization: Bearer Token</el-option>
            <el-option label="URL Token（源站不能设置请求头时使用）" value="query"><BusinessIcon kind="auth" value="query" />URL Token（源站不能设置请求头时使用）</el-option>
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="form.source_auth_enabled && form.source_type !== 'gitee' && form.source_auth === 'header'"
          label="密钥请求头名称"
        >
          <el-input
            v-model="form.source_token_header"
            placeholder="X-Webhook-Token"
          />
        </el-form-item>
        <el-form-item
          v-if="form.source_auth_enabled"
          :label="sourceSecretSet ? '更换回调密钥（留空保留）' : '回调密钥'"
          :required="!sourceSecretSet"
        >
          <el-input
            v-model="form.source_secret"
            type="password"
            show-password
            autocomplete="new-password"
            placeholder="至少 8 位，源站需配置相同密钥"
          />
          <div v-if="form.source_type === 'gitee'" class="field-help">
            填入 Gitee WebHook 的密码，兼容 X-Gitee-Token。
          </div>
          <div v-else-if="form.source_auth === 'query'" class="field-help">
            在生成 URL 后追加 &amp;token=经过 URL 编码的密钥；完整 URL
            属于凭证，请勿公开。保存后密钥不回显。
          </div>
          <div v-else-if="form.source_auth === 'bearer'" class="field-help">
            源站请求头设置 Authorization: Bearer 你的密钥。
          </div>
          <div v-else class="field-help">
            源站请求头 {{ form.source_token_header }} 的值填写此密钥。
          </div>
        </el-form-item>
        <el-form-item
          v-if="form.source_type === 'gitee'"
          label="接收事件"
          required
        >
          <el-checkbox-group v-model="form.events">
            <el-checkbox
              v-for="(label, value) in giteeEvents"
              :key="value"
              :value="value"
            >
              <BusinessIcon kind="event" :value="String(value)" />{{ label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-else label="接收事件（留空接收全部，多个用逗号分隔）">
          <el-input
            v-model="customEvents"
            :placeholder="
              form.source_type === 'nightingale'
                ? 'alert, recovery, alert_batch'
                : '如 service.error, service.recovered'
            "
          />
          <div class="field-help">
            优先读取
            X-Webhook-Event。夜莺自动识别告警/恢复/批量事件；通用回调读取
            event_type 或 event，缺失时为 webhook。
          </div>
        </el-form-item>
        <el-form-item label="源站附加信息（JSON）">
          <el-input v-model="sourceInfo" type="textarea" :rows="2" />
        </el-form-item>
        <h3 class="form-section"><span>02</span> 消息处理</h3>
        <el-form-item label="启用 LLM 处理">
          <el-switch v-model="form.llm_enabled" /><span class="inline-hint">关闭后直接使用源站模板的内容</span>
        </el-form-item>
        <el-form-item label="源站消息模板">
          <el-input v-model="form.source_template" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="form.llm_enabled" label="LLM 提示词">
          <el-input v-model="form.llm_prompt" type="textarea" :rows="4" />
          <div class="field-help">使用个人设置中的 Host、API Key 与模型。</div>
        </el-form-item>
        <h3 class="form-section"><span>03</span> 目标群机器人</h3>
        <el-form-item label="目标平台">
          <el-radio-group v-model="form.target_type" @change="changeTarget">
            <el-radio-button
              v-for="(label, value) in targets"
              :key="value"
              :value="value"
            >
              <BusinessIcon kind="target" :value="value" />{{ label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          :label="
            editing
              ? '目标 Webhook URL（留空保留；切换平台时必填）'
              : '目标 Webhook URL'
          "
          :required="!editing"
        >
          <el-input
            v-model="form.target_url"
            type="password"
            show-password
            autocomplete="off"
            placeholder="粘贴群机器人的完整 HTTPS Webhook URL"
          />
        </el-form-item>
        <el-form-item
          v-if="form.target_type !== 'wecom'"
          label="机器人签名密钥（选填，留空保留）"
        >
          <el-input
            v-model="form.target_secret"
            type="password"
            show-password
            placeholder="启用加签验证的机器人需要填写"
          />
        </el-form-item>
        <el-form-item label="@所有人">
          <el-switch v-model="form.target_mentions.all" /><span
            class="inline-hint"
          >需群机器人具有相应权限</span>
        </el-form-item>
        <el-form-item
          :label="
            form.target_type === 'feishu'
              ? '@成员 Open ID（ou_ 开头）'
              : '@成员用户 ID'
          "
        >
          <el-input
            v-model="mentionIds"
            :disabled="form.target_mentions.all"
            type="textarea"
            :rows="2"
            placeholder="多个 ID 用换行或逗号分隔，留空不 @"
          />
          <div class="field-help">
            {{
              form.target_type === "feishu"
                ? "填写该机器人可识别的群成员 Open ID，不是姓名、手机号或普通 user_id。"
                : "填写目标平台的群成员 user ID，不是显示名称。"
            }}
          </div>
        </el-form-item>
        <el-form-item v-if="form.target_type !== 'feishu'" label="@成员手机号">
          <el-input
            v-model="mentionMobiles"
            :disabled="form.target_mentions.all"
            type="textarea"
            :rows="2"
            placeholder="群成员绑定的手机号，多个用换行或逗号分隔"
          />
        </el-form-item>
        <p class="field-help">
          @ 配置由系统在 LLM
          处理之后加入消息。切换目标平台会清空成员配置，避免使用错误平台的 ID。
        </p>
        <el-form-item label="目标消息模板">
          <div v-if="form.source_type === 'nightingale' && form.target_type === 'feishu'" class="field-help">夜莺单条告警保留原始字段、时间和事件链接；此模板用于下方 AI 分析区，建议仅填写 llm_output 变量。源站地址用于生成夜莺事件链接。</div>
          <el-input v-model="form.target_template" type="textarea" :rows="4" />
          <div v-pre class="field-help">
            支持 {{ payload }}、{{ event }}、{{ source_url }}、{{
            source_type
            }}、{{ source_name }}、{{ llm_output }}，以及
            {{ payload.title }}、{{payload.events.0.rule_name}} 等 JSON
            路径。模板生成卡片正文：飞书、钉钉支持 Markdown；企业微信使用原生模板卡片文本布局。卡片标题取规则名称，飞书告警为红色、恢复为绿色。
          </div>
        </el-form-item>
        <el-form-item label="启用此规则">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">
          {{ editing ? "保存更改" : "创建并生成 URL" }}
        </el-button>
      </template>
    </el-drawer>
  </section>
</template>
