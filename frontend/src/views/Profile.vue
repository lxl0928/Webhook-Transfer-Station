<script setup lang="ts">
import BusinessIcon from "../components/BusinessIcon.vue";
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api, formatDate, type Profile } from "../api";

const router = useRouter();
const profile = ref<Profile | null>(null);
const basic = reactive({ real_name: "", phone: "" });
const llm = reactive({ llm_host: "", llm_model: "", llm_api_key: "" });
const passwords = reactive({
  current_password: "",
  new_password: "",
  confirm: "",
});
const saving = ref("");
const checking = ref(false);
const health = ref("尚未检测");
const healthStatus = ref("unchecked");
async function load() {
  try {
    const { data } = await api.get<Profile>("/api/users/me");
    profile.value = data;
    Object.assign(basic, { real_name: data.real_name, phone: data.phone });
    Object.assign(llm, {
      llm_host: data.llm_host,
      llm_model: data.llm_model,
      llm_api_key: "",
    });
  } catch {
    /* Shared error handler. */
  }
}
async function save(section: string) {
  let body: Record<string, string>;
  if (section === "password") {
    if (
      !passwords.current_password ||
      passwords.new_password.length < 10 ||
      passwords.new_password !== passwords.confirm
    ) {
      ElMessage.warning("请输入当前密码，新密码至少 10 位且两次输入一致");
      return;
    }
    body = {
      current_password: passwords.current_password,
      new_password: passwords.new_password,
    };
  } else if (section === "llm") {
    body = { llm_host: llm.llm_host, llm_model: llm.llm_model };
    if (llm.llm_api_key) body.llm_api_key = llm.llm_api_key;
  } else body = { ...basic };
  saving.value = section;
  try {
    await api.patch("/api/users/me", body);
    ElMessage.success(
      section === "password" ? "密码已更新，请重新登录" : "设置已保存",
    );
    if (section === "password") {
      sessionStorage.removeItem("station-token");
      await router.push("/login");
    } else await load();
  } catch {
    /* Shared error handler. */
  } finally {
    saving.value = "";
  }
}
async function check() {
  checking.value = true;
  healthStatus.value = "processing";
  try {
    const { data } = await api.post("/api/health/llm");
    healthStatus.value = "ok";
    health.value = `LLM 连接正常 · ${data.cost_ms} ms`;
    ElMessage.success(health.value);
  } catch {
    healthStatus.value = "unavailable";
    health.value = "LLM 不可用，请检查已保存的配置";
  } finally {
    checking.value = false;
  }
}
async function serviceHealth() {
  try {
    const { data } = await api.get("/health/ready");
    ElMessage.success(`后端：${data.backend}；PostgreSQL：${data.postgresql}`);
  } catch {
    /* Shared error handler. */
  }
}
onMounted(load);
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <div class="eyebrow">WORKSPACE SETTINGS</div>
        <h1>个人设置</h1>
        <p>管理账户资料，以及所有中转规则使用的默认 LLM。</p>
      </div>
      <el-button @click="serviceHealth">检测服务健康</el-button>
    </div>
    <div class="settings-grid">
      <div class="panel settings-panel">
        <div class="settings-heading">
          <h3><BusinessIcon kind="feature" value="member" />账户资料</h3>
          <p>你的管理员账户信息</p>
        </div>
        <el-form label-position="top" @submit.prevent="save('basic')">
          <el-form-item label="用户名">
            <el-input
              :model-value="profile?.username"
              disabled
            />
          </el-form-item><el-form-item label="真实姓名">
            <el-input
              v-model="basic.real_name"
              maxlength="100"
            />
          </el-form-item><el-form-item label="手机号">
            <el-input v-model="basic.phone" maxlength="32" />
          </el-form-item>
          <p class="field-help">
            最近登录：{{ formatDate(profile?.last_login_at ?? null) }}
          </p>
          <el-button
            type="primary"
            native-type="submit"
            :loading="saving === 'basic'"
          >
            保存资料
          </el-button>
        </el-form>
      </div>
      <div class="panel settings-panel">
        <div class="settings-heading">
          <h3>默认 LLM 配置 <span class="ai-tag"><BusinessIcon kind="feature" value="ai" />AI</span></h3>
          <p>兼容 OpenAI Chat Completions 格式的服务</p>
        </div>
        <el-form label-position="top" @submit.prevent="save('llm')">
          <el-form-item label="LLM Host">
            <el-input
              v-model="llm.llm_host"
              placeholder="https://your-provider.example/v1"
            /><span class="field-help">填写含 API 前缀的基础地址，不含
              /chat/completions；域名需由运维加入允许列表。</span>
          </el-form-item><el-form-item label="模型名称">
            <el-input
              v-model="llm.llm_model"
              placeholder="填写服务商提供的模型 ID"
            />
          </el-form-item><el-form-item
            :label="
              profile?.llm_api_key_set
                ? 'API Key（已配置，留空保留）'
                : 'API Key'
            "
          >
            <el-input
              v-model="llm.llm_api_key"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="填写模型服务 API Key"
            />
          </el-form-item>
          <div class="toolbar-actions">
            <el-button
              type="primary"
              native-type="submit"
              :loading="saving === 'llm'"
            >
              保存配置
            </el-button><el-button :loading="checking" @click="check">
              检测已保存配置
            </el-button>
          </div>
          <p class="field-help">
            <BusinessIcon kind="status" :value="healthStatus" />{{ checking ? "正在检测" : health }}。检测会发起一次小型模型调用。
          </p>
        </el-form>
      </div>
      <div class="panel settings-panel">
        <div class="settings-heading">
          <h3><BusinessIcon kind="auth" value="bearer" />修改密码</h3>
          <p>修改后，已有登录凭证将全部失效。</p>
        </div>
        <el-form label-position="top" @submit.prevent="save('password')">
          <el-form-item label="当前密码">
            <el-input
              v-model="passwords.current_password"
              type="password"
              show-password
              autocomplete="current-password"
            />
          </el-form-item><el-form-item label="新密码">
            <el-input
              v-model="passwords.new_password"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="至少 10 位"
            />
          </el-form-item><el-form-item label="确认新密码">
            <el-input
              v-model="passwords.confirm"
              type="password"
              show-password
              autocomplete="new-password"
            />
          </el-form-item><el-button
            type="primary"
            native-type="submit"
            :loading="saving === 'password'"
          >
            更新密码
          </el-button>
        </el-form>
      </div>
      <div class="settings-note">
        <div class="eyebrow">GOOD TO KNOW</div>
        <h2>一次配置，<br />贯穿所有消息。</h2>
        <p>
          中转规则使用你在这里设置的模型服务。每条消息在接收时保存配置快照，保证处理过程可追踪。
        </p>
        <p>
          第一次登录后，请更新默认密码。API Key
          与机器人密钥均加密保存在数据库中。
        </p>
      </div>
    </div>
  </section>
</template>
