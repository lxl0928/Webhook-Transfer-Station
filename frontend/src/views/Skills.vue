<script setup lang="ts">
import BusinessIcon from "../components/BusinessIcon.vue";
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
interface Skill {
  id: string;
  name: string;
  description: string;
  instructions: string;
  tools: string[];
  builtin: boolean;
  enabled: boolean;
}
interface Tool {
  name: string;
  description: string;
  mutation: boolean;
}
const items = ref<Skill[]>([]),
  tools = ref<Tool[]>([]),
  editing = ref(false),
  saving = ref(false);
const id = ref(""),
  builtin = ref(false);
const form = reactive({
  name: "",
  description: "",
  instructions: "",
  tools: [] as string[],
  enabled: true,
});
async function load() {
  items.value = (await api.get("/api/skills")).data.items;
}
onMounted(async () => {
  await load();
  tools.value = (await api.get("/api/skills/tools")).data.items;
});
function edit(skill?: Skill) {
  id.value = skill?.id || "";
  builtin.value = skill?.builtin || false;
  Object.assign(form, {
    name: skill?.name || "",
    description: skill?.description || "",
    instructions: skill?.instructions || "",
    tools: [...(skill?.tools || [])],
    enabled: skill?.enabled ?? true,
  });
  editing.value = true;
}
async function save() {
  saving.value = true;
  try {
    if (id.value) await api.put(`/api/skills/${id.value}`, form);
    else await api.post("/api/skills", form);
    editing.value = false;
    await load();
    ElMessage.success("Skill 已保存");
  } finally {
    saving.value = false;
  }
}
async function remove(skill: Skill) {
  try {
    await ElMessageBox.confirm(
      `确定${skill.builtin ? "恢复默认" : "删除"} ${skill.name}？`,
      "确认操作",
    );
  } catch {
    return;
  }
  if (skill.builtin) await api.post(`/api/skills/${skill.id}/reset`);
  else await api.delete(`/api/skills/${skill.id}`);
  await load();
}
async function toggle(skill: Skill) {
  await api.patch(`/api/skills/${skill.id}`, { enabled: !skill.enabled });
  await load();
}
async function download(skill: Skill) {
  const response = await api.get(`/api/skills/${skill.id}/export`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${skill.name}-SKILL.md`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>Skill 管理</h1>
      <p>让助手理解你的工作方式，并限定它可以使用的工具。</p>
    </div>
    <el-button type="primary" @click="edit()">新增 Skill</el-button>
  </div>
  <el-alert
    title="Skill 由操作说明和工具白名单组成；不执行脚本。修改数据仍需在聊天中确认。"
    type="info"
    show-icon
    :closable="false"
  />
  <div class="skill-grid">
    <article v-for="skill in items" :key="skill.id" class="skill-card">
      <div>
        <el-tag size="small" :type="skill.builtin ? 'info' : 'success'">
          <BusinessIcon kind="skill" :value="skill.builtin ? 'builtin' : 'custom'" />{{ skill.builtin ? "内置" : "自定义" }}
        </el-tag><el-button link @click="toggle(skill)">
          <BusinessIcon kind="status" :value="skill.enabled ? 'enabled' : 'disabled'" />{{ skill.enabled ? "已启用 · 点击停用" : "已停用 · 点击启用" }}
        </el-button>
      </div>
      <h3>{{ skill.name }}</h3>
      <p>{{ skill.description }}</p>
      <small>{{ skill.tools.length }} 个授权工具</small>
      <div class="skill-actions">
        <el-button link type="primary" @click="edit(skill)">编辑</el-button><el-button link @click="download(skill)">导出 SKILL.md</el-button><el-button
          link
          :type="skill.builtin ? 'warning' : 'danger'"
          @click="remove(skill)"
        >
          {{ skill.builtin ? "恢复默认" : "删除" }}
        </el-button>
      </div>
    </article>
  </div>
  <el-drawer
    v-model="editing"
    :title="id ? '编辑 Skill' : '新增 Skill'"
    size="min(620px, 100%)"
  >
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="名称（小写英文、数字和连字符，3–64 字符）">
        <el-input v-model="form.name" :disabled="builtin" maxlength="64" />
      </el-form-item>
      <el-form-item label="功能描述">
        <el-input v-model="form.description" maxlength="500" />
      </el-form-item>
      <el-form-item label="操作说明（Markdown）">
        <el-input
          v-model="form.instructions"
          type="textarea"
          :rows="10"
          maxlength="8000"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label="允许调用的工具">
        <el-select v-model="form.tools" multiple filterable style="width: 100%">
          <el-option
            v-for="tool in tools"
            :key="tool.name"
            :label="`${tool.name} · ${tool.mutation ? '需确认' : '查询'}`"
            :value="tool.name"
            :title="tool.description"
          >
            <BusinessIcon kind="tool" :value="tool.mutation ? 'mutation' : 'read'" />{{ tool.name }} · {{ tool.mutation ? '需确认' : '查询' }}
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.enabled" />
      </el-form-item>
      <el-button type="primary" :loading="saving" @click="save">
        保存 Skill
      </el-button>
    </el-form>
  </el-drawer>
</template>
<style scoped>
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
  margin-top: 24px;
}
.skill-card {
  background: white;
  border: 1px solid #e5eaf1;
  padding: 22px;
  border-radius: 14px;
}
.skill-card > div:first-child {
  display: flex;
  justify-content: space-between;
}
.skill-card h3 {
  font-size: 16px;
  overflow-wrap: anywhere;
}
.skill-card p {
  color: #64748b;
  min-height: 44px;
  line-height: 1.6;
}
.skill-card small {
  color: #64748b;
}
.skill-actions {
  display: flex;
  margin-top: 22px;
  flex-wrap: wrap;
}
</style>
