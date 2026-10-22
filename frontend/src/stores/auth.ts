import { defineStore } from "pinia";
import {
  clearAuthTokens,
  endAuthDocument,
  readOptionalAccessToken,
  saveAuthTokens,
  USER_EMAIL_KEY,
} from "../api/authToken";
import { currentUser, login, register, type AuthUser, type LoginRequest, type RegisterRequest } from "../api/auth";
import { setAuthInvalidHandler } from "../api/http";

interface AuthState {
  accessToken: string;
  userEmail: string;
  user: AuthUser | null;
  loading: boolean;
  errorMessage: string;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    accessToken: readOptionalAccessToken(),
    userEmail: window.localStorage.getItem(USER_EMAIL_KEY) || "",
    user: null,
    loading: false,
    errorMessage: "",
  }),

  getters: {
    isAuthenticated: (state) => state.accessToken.trim().length > 0,
    isAdmin: (state) => state.user?.role === "ADMIN",
    displayEmail: (state) => state.user?.email || state.userEmail,
  },

  actions: {
    async loadCurrentUser(force = false) {
      if (!this.isAuthenticated) return null;
      if (!force && this.user) return this.user;
      try { this.user = await currentUser(); }
      catch (error) { this.user = null; throw error; }
      return this.user;
    },
    async login(request: LoginRequest, nextPath?: string) {
      this.loading = true;
      this.errorMessage = "";
      try {
        const session = await login(request);
        saveAuthTokens(session.accessToken, session.refreshToken, session.user.email, nextPath);
        this.accessToken = session.accessToken;
        this.userEmail = session.user.email;
        this.user = session.user;
        return session;
      } finally {
        this.loading = false;
      }
    },

    async register(request: RegisterRequest) {
      this.loading = true;
      this.errorMessage = "";
      try {
        return await register(request);
      } finally {
        this.loading = false;
      }
    },

    logout() {
      clearAuthTokens();
      endAuthDocument("/login");
      this.accessToken = "";
      this.userEmail = "";
      this.user = null;
      this.errorMessage = "";
    },
  },
});

setAuthInvalidHandler(() => {
  const authStore = useAuthStore();
  authStore.logout();
});
