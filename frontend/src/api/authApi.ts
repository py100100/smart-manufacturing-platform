const AUTH_KEY = 'sm_auth';
const USERS_KEY = 'sm_users';

interface StoredUser {
  username: string;
  password: string;
  email: string;
  createdAt: string;
}

export interface AuthState {
  username: string;
  email: string;
  loggedInAt: string;
}

const DEFAULT_USER: StoredUser = {
  username: 'admin',
  password: '1234',
  email: 'admin@smartmfg.com',
  createdAt: 'default',
};

function normalizeUsername(username: string): string {
  return username.trim();
}

function getUsers(): StoredUser[] {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    const saved = raw ? (JSON.parse(raw) as StoredUser[]) : [];
    const hasDefault = saved.some((u) => u.username === DEFAULT_USER.username);
    return hasDefault ? saved : [DEFAULT_USER, ...saved];
  } catch {
    return [DEFAULT_USER];
  }
}

function saveUsers(users: StoredUser[]): void {
  const withoutDefault = users.filter((u) => u.username !== DEFAULT_USER.username);
  localStorage.setItem(USERS_KEY, JSON.stringify(withoutDefault));
}

function createAuthState(user: StoredUser): AuthState {
  return {
    username: user.username,
    email: user.email,
    loggedInAt: new Date().toISOString(),
  };
}

export function login(username: string, password: string): AuthState {
  const name = normalizeUsername(username);
  const pass = password.trim();
  if (!name || !pass) {
    throw new Error('用户名和密码不能为空');
  }
  const user = getUsers().find((u) => u.username === name);
  if (!user || user.password !== pass) {
    throw new Error('用户名或密码错误');
  }
  const state = createAuthState(user);
  localStorage.setItem(AUTH_KEY, JSON.stringify(state));
  return state;
}

export function register(username: string, password: string, email: string): AuthState {
  const name = normalizeUsername(username);
  const pass = password.trim();
  if (!name || !pass) {
    throw new Error('用户名和密码不能为空');
  }
  if (pass.length < 4) {
    throw new Error('密码至少 4 位');
  }
  const users = getUsers();
  if (users.some((u) => u.username === name)) {
    throw new Error('用户名已存在');
  }
  const newUser: StoredUser = {
    username: name,
    password: pass,
    email: email.trim() || `${name}@smartmfg.com`,
    createdAt: new Date().toISOString(),
  };
  saveUsers([...users, newUser]);
  const state = createAuthState(newUser);
  localStorage.setItem(AUTH_KEY, JSON.stringify(state));
  return state;
}

export function logout(): void {
  localStorage.removeItem(AUTH_KEY);
}

export function getAuth(): AuthState | null {
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthState;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getAuth() !== null;
}
