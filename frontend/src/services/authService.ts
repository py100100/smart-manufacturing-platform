import type { AuthState } from '../api/authApi';
import { getAuth, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/authApi';

export type { AuthState };

export const authService = {
  login: apiLogin,
  register: apiRegister,
  logout: apiLogout,
  getAuth,
  isAuthenticated: () => getAuth() !== null,
};
