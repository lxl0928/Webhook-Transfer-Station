<script setup lang="ts">
import { computed, type Component } from "vue";
import {
  Bell,
  ChatDotRound,
  ChatLineRound,
  CircleCheckFilled,
  CircleCloseFilled,
  Clock,
  Collection,
  Connection,
  Document,
  EditPen,
  FolderOpened,
  Key,
  Link,
  Loading,
  Lock,
  MagicStick,
  Monitor,
  MoreFilled,
  Operation,
  Promotion,
  QuestionFilled,
  Select,
  Setting,
  SwitchButton,
  User,
  UserFilled,
  WarningFilled,
} from "@element-plus/icons-vue";

type Kind =
  | "source"
  | "target"
  | "status"
  | "event"
  | "skill"
  | "tool"
  | "auth"
  | "feature";
const props = defineProps<{ kind: Kind; value: string }>();
const icons: Record<Kind, Record<string, Component>> = {
  source: { gitee: FolderOpened, nightingale: Monitor, generic: Connection },
  target: { feishu: Promotion, wecom: ChatDotRound, dingtalk: Bell },
  status: {
    enabled: CircleCheckFilled,
    disabled: CircleCloseFilled,
    pending: Clock,
    processing: Loading,
    succeeded: CircleCheckFilled,
    failed: CircleCloseFilled,
    ignored: MoreFilled,
    rejected: CircleCloseFilled,
    expired: Clock,
    ok: CircleCheckFilled,
    unavailable: WarningFilled,
    unchecked: QuestionFilled,
  },
  event: {
    webhook: Connection,
    alert: WarningFilled,
    recovery: CircleCheckFilled,
    alert_batch: Collection,
    push: Promotion,
    pull_request: Operation,
    tag: Collection,
    comment: ChatLineRound,
  },
  skill: { builtin: Collection, custom: EditPen },
  tool: { read: Document, mutation: Lock },
  auth: { header: Key, bearer: Lock, query: Link },
  feature: {
    ai: MagicStick,
    template: Document,
    all: UserFilled,
    member: User,
    settings: Setting,
    logout: SwitchButton,
    confirmed: Select,
  },
};
const icon = computed(() => icons[props.kind][props.value] ?? QuestionFilled);
const tone = computed(() => {
  if (props.kind === "status") {
    if (["enabled", "succeeded", "ok"].includes(props.value)) return "success";
    if (["disabled", "failed", "rejected", "unavailable"].includes(props.value))
      return "danger";
    if (["pending", "expired"].includes(props.value)) return "warning";
    if (props.value === "processing") return "primary";
    return "muted";
  }
  if (props.kind === "event" && props.value === "alert") return "warning";
  if (props.kind === "event" && props.value === "recovery") return "success";
  return "inherit";
});
</script>

<template>
  <el-icon
    class="business-icon"
    :class="[
      `tone-${tone}`,
      { spinning: kind === 'status' && value === 'processing' },
    ]"
    aria-hidden="true"
  >
    <component :is="icon" />
  </el-icon>
</template>

<style scoped>
.business-icon {
  vertical-align: -0.15em;
  flex-shrink: 0;
  margin-inline-end: 5px;
}
.tone-success {
  color: #23834b;
}
.tone-danger {
  color: #d53a40;
}
.tone-warning {
  color: #a56a0a;
}
.tone-primary {
  color: var(--el-color-primary);
}
.tone-muted {
  color: #7a8492;
}
.spinning {
  animation: business-spin 1.5s linear infinite;
}
@keyframes business-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinning {
    animation: none;
  }
}
</style>
