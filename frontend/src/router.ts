import { createRouter, createWebHashHistory } from "vue-router";
import { token } from "./api";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/skills", component: () => import("./views/Skills.vue") },
    { path: "/login", component: () => import("./views/Login.vue") },
    { path: "/", redirect: "/webhooks" },
    { path: "/webhooks", component: () => import("./views/Webhooks.vue") },
    { path: "/logs", component: () => import("./views/Logs.vue") },
    { path: "/profile", component: () => import("./views/Profile.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
router.beforeEach((to) => {
  if (to.path !== "/login" && !token()) return "/login";
  if (to.path === "/login" && token()) return "/webhooks";
});
export default router;
