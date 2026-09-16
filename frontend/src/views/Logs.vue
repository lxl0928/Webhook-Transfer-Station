<script setup lang="ts">
import BusinessIcon from "../components/BusinessIcon.vue";
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import {
  api,
  copy,
  events,
  formatDate,
  pretty,
  statuses,
  type Log,
} from "../api";

const route = useRoute();
const rows = ref<Log[]>([]);
const total = ref(0);
const page = ref(1);
const wid = ref(String(route.query.wid ?? ""));
const status = ref("");
const trace = ref("");
const dates = ref<[string, string] | null>(null);
const busy = ref(false);
const auto = ref(false);
const drawer = ref(false);
const detail = ref<Log | null>(null);
const retrying = ref(false);
let timer: ReturnType<typeof setInterval>;
async function load(quiet = false) {
  if (busy.value) return;
  busy.value = !quiet;
  try {
    const { data } = await api.get("/api/webhook-logs", {
      params: {
        page: page.value,
        wid: wid.value || undefined,
        status: status.value || undefined,
        trace_id: trace.value || undefined,
        start: dates.value?.[0],
        end: dates.value?.[1],
      },
    });
    rows.value = data.items;
    total.value = data.total;
  } catch {
    /* Shared error handler. */
  } finally {
    busy.value = false;
  }
}
async function show(log: Log) {
  try {
    detail.value = (await api.get(`/api/webhook-logs/${log.id}`)).data;
    drawer.value = true;
  } catch {
    /* Shared error handler. */
  }
}
async function retry() {
  if (!detail.value) return;
  try {
    await ElMessageBox.confirm(
      "网络超时的消息可能已被目标平台接收。确认后将使用接收时的配置重新处理，可能产生重复消息。",
      "重试这条消息？",
      {
        confirmButtonText: "确认重试",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }
  retrying.value = true;
  try {
    await api.post(`/api/webhook-logs/${detail.value.id}/retries`);
    ElMessage.success("已重新入队");
    await show(detail.value);
    await load();
  } catch {
    /* Shared error handler. */
  } finally {
    retrying.value = false;
  }
}
function search() {
  page.value = 1;
  void load();
}
function reset() {
  wid.value = "";
  status.value = "";
  trace.value = "";
  dates.value = null;
  search();
}
function tagType(value: string) {
  return value === "succeeded"
    ? "success"
    : value === "failed"
      ? "danger"
      : value === "processing"
        ? "warning"
        : "info";
}
onMounted(() => {
  void load();
  timer = setInterval(() => {
    if (auto.value && !document.hidden) void load(true);
  }, 5000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <div class="eyebrow">MESSAGE ACTIVITY</div>
        <h1>消息日志</h1>
        <p>从接收到投递，让每条消息的去向清晰可见。</p>
      </div>
      <div class="toolbar-actions">
        <span class="muted">自动刷新</span><el-switch v-model="auto" /><el-button :icon="Refresh" @click="load()">
          刷新
        </el-button>
      </div>
    </div>
    <div class="panel">
      <div class="log-filters">
        <el-input
          v-model="wid"
          placeholder="Webhook ID"
          clearable
          @keyup.enter="search"
        /><el-select
          v-model="status"
          placeholder="全部状态"
          clearable
          @change="search"
        >
          <template v-if="status" #prefix><BusinessIcon kind="status" :value="status" /></template>
          <el-option
            v-for="(label, value) in statuses"
            :key="value"
            :label="label"
            :value="value"
          >
            <BusinessIcon kind="status" :value="value" />{{ label }}
          </el-option>
        </el-select><el-input
          v-model="trace"
          placeholder="Trace ID"
          clearable
          @keyup.enter="search"
        /><el-date-picker
          v-model="dates"
          type="datetimerange"
          start-placeholder="接收起始时间"
          end-placeholder="接收结束时间"
          value-format="YYYY-MM-DDTHH:mm:ssZ"
        /><el-button type="primary" :icon="Search" @click="search">
          查询
        </el-button><el-button @click="reset">重置</el-button>
      </div>
      <el-table
        v-loading="busy"
        :data="rows"
        empty-text="暂无消息，接收 Gitee、夜莺或自定义服务回调后将在这里显示"
        @row-click="show"
      >
        <el-table-column label="中转规则" min-width="170">
          <template #default="{ row }">
            <b>{{ row.webhook_name }}</b>
            <div class="table-sub">{{ row.wid.slice(0, 12) }}…</div>
          </template>
        </el-table-column>
        <el-table-column label="事件" min-width="125">
          <template #default="{ row }">
            <BusinessIcon kind="event" :value="row.event" />{{ events[row.event] ?? row.event }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)" effect="light">
              <BusinessIcon kind="status" :value="row.status" />{{ statuses[row.status] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="接收时间" min-width="185">
          <template #default="{ row }">
            {{
              formatDate(row.received_at)
            }}
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="105">
          <template #default="{ row }">
            {{
              row.cost_ms == null ? "—" : `${row.cost_ms} ms`
            }}
          </template>
        </el-table-column>
        <el-table-column label="尝试次数" width="90" prop="attempts" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="show(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ total }} 条消息</span><el-pagination
          v-model:current-page="page"
          :total="total"
          :page-size="20"
          layout="prev, pager, next"
          @current-change="load()"
        />
      </div>
    </div>
    <el-drawer v-model="drawer" title="消息处理详情" size="min(820px, 100%)">
      <template v-if="detail">
        <div class="detail-title">
          <h2>{{ detail.webhook_name }}</h2>
          <el-tag :type="tagType(detail.status)">
            <BusinessIcon kind="status" :value="detail.status" />{{ statuses[detail.status] ?? detail.status }}
          </el-tag>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="Trace ID">
            <code>{{ detail.trace_id }}</code><el-button link type="primary" @click="copy(detail.trace_id)">
              复制
            </el-button>
          </el-descriptions-item><el-descriptions-item label="接收时间">
            {{
              formatDate(detail.received_at)
            }}
          </el-descriptions-item><el-descriptions-item label="处理开始">
            {{
              formatDate(detail.started_at)
            }}
          </el-descriptions-item><el-descriptions-item label="投递成功">
            {{
              formatDate(detail.output_at)
            }}
          </el-descriptions-item><el-descriptions-item label="处理结束">
            {{
              formatDate(detail.finished_at)
            }}
          </el-descriptions-item><el-descriptions-item label="耗时 / 尝试">
            {{ detail.cost_ms ?? "—" }} ms /
            {{ detail.attempts }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="detail.error"
          :title="detail.error"
          type="error"
          :closable="false"
          show-icon
          class="space-top"
        />
        <h3>源站输入</h3>
        <pre>{{ pretty(detail.input_payload) }}</pre>
        <h3>LLM / 源模板处理结果</h3>
        <pre>{{ detail.llm_output || "暂无数据" }}</pre>
        <h3>目标站输出</h3>
        <pre>{{ pretty(detail.output_payload) }}</pre>
        <h3>目标站响应</h3>
        <pre>{{ pretty(detail.target_response) }}</pre>
      </template>
      <template #footer>
        <el-button v-if="detail" @click="show(detail)">刷新详情</el-button><el-button
          v-if="detail?.status === 'failed'"
          type="primary"
          :loading="retrying"
          @click="retry"
        >
          重试消息
        </el-button><el-button @click="drawer = false">关闭</el-button>
      </template>
    </el-drawer>
  </section>
</template>
