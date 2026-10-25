import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import ui from "@nuxt/ui/vue-plugin";
import App from "./App.vue";
import Catalog from "./pages/Catalog.vue";
import Detail from "./pages/Detail.vue";
import Directory from "./pages/Directory.vue";
import Admin from "./pages/Admin.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: Catalog },
    { path: "/works/:id", component: Detail },
    { path: "/people", component: Directory, props: { kind: "people" } },
    {
      path: "/collections",
      component: Directory,
      props: { kind: "collections" },
    },
    { path: "/admin/:section?", component: Admin },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
createApp(App).use(router).use(ui).mount("#app");
