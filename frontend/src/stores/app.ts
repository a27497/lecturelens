import { defineStore } from "pinia";

export const useAppStore = defineStore("app", {
  state: () => ({
    appName: "LectureLens",
    initialized: true,
  }),
});
