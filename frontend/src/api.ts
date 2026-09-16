import axios from "axios";
import { ElMessage } from "element-plus";

export const api = axios.create({ timeout: 65000 });
export const token = () => sessionStorage.getItem("station-token");
api.interceptors.request.use((config) => {
  if (token()) config.headers.Authorization = `Bearer ${token()}`;
  config.headers["X-Trace-Id"] =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return config;
});
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    const trace = error.response?.headers?.["x-trace-id"];
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg: string }) => item.msg).join("；")
          : "请求失败，请检查网络或服务状态";
    ElMessage.error(`${message}${trace ? `（Trace: ${trace}）` : ""}`);
    if (
      error.response?.status === 401 &&
      !error.config.url.includes("/auth/login")
    ) {
      sessionStorage.removeItem("station-token");
      window.location.hash = "#/login";
    }
    return Promise.reject(error);
  },
);

export interface Profile {
  username: string;
  real_name: string;
  phone: string;
  llm_host: string;
  llm_model: string;
  llm_api_key_set: boolean;
  last_login_at: string | null;
}
export interface Mentions {
  all: boolean;
  user_ids: string[];
  mobiles: string[];
}
export const sources: Record<string, string> = {
  gitee: "Gitee",
  nightingale: "夜莺",
  generic: "自定义服务",
};

export interface Hook {
  source_type: "gitee" | "nightingale" | "generic";
  source_auth: "header" | "bearer" | "query";
  source_token_header: string;
  target_mentions: Mentions;
  wid: string;
  name: string;
  source_url: string;
  source_info: Record<string, unknown>;
  source_template: string;
  events: string[];
  llm_enabled: boolean;
  llm_prompt: string;
  target_type: "feishu" | "wecom" | "dingtalk";
  target_template: string;
  enabled: boolean;
  url: string;
  updated_at: string;
  target_secret_set: boolean;
}
export interface Log {
  id: string;
  wid: string;
  webhook_name: string;
  trace_id: string;
  event: string;
  status: string;
  attempts: number;
  error: string | null;
  received_at: string;
  started_at: string | null;
  output_at: string | null;
  finished_at: string | null;
  cost_ms: number | null;
  input_payload?: unknown;
  output_payload?: unknown;
  llm_output?: string;
  target_response?: unknown;
}
export const targets: Record<string, string> = {
  feishu: "飞书",
  wecom: "企业微信",
  dingtalk: "钉钉",
};
export const events: Record<string, string> = {
  webhook: "通用事件",
  alert: "告警触发",
  recovery: "告警恢复",
  alert_batch: "批量告警",
  push: "代码提交",
  pull_request: "Pull Request",
  tag: "Tag",
  comment: "评论 / Review Comment",
};
export const statuses: Record<string, string> = {
  pending: "等待处理",
  processing: "处理中",
  succeeded: "投递成功",
  failed: "处理失败",
  ignored: "已忽略",
};
export const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
export const pretty = (value: unknown) =>
  value == null ? "暂无数据" : JSON.stringify(value, null, 2);
export async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制");
  } catch {
    ElMessage.warning(
      "浏览器不允许复制，请选中文本手动复制（HTTPS 可启用复制功能）",
    );
  }
}
