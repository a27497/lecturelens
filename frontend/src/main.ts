import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import { router } from "./router";
import "./style.css";
import { installAuthSessionBoundary } from "./api/authToken";

const app = createApp(App).use(createPinia()).use(router).use(ElementPlus);
installAuthSessionBoundary((path) => {
  app.unmount();
  document.getElementById("app")?.replaceChildren();
  window.stop();
  window.location.replace(path);
});
app.mount("#app");
