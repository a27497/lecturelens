import { defineStore } from "pinia";
import {
  clearAuthTokens,
  readOptionalAccessToken,
  saveAuthTokens,
  USER_EMAIL_KEY,
} from "../api/authToken";
import { login, register, type AuthUser, type LoginRequest, type RegisterRequest } from "../api/auth";
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
    displayEmail: (state) => state.user?.email || state.userEmail,
  },

  actions: {
    async login(request: LoginRequest) {
      this.loading = true;
      this.errorMessage = "";
      try {
        const session = await login(request);
        saveAuthTokens(session.accessToken, session.refreshToken, session.user.email);
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
