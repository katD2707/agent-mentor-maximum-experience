/** Where the session token lives. localStorage for now; a Tauri store can implement this later. */
export interface TokenStorage {
  get(): Promise<string | null>;
  set(token: string): Promise<void>;
  clear(): Promise<void>;
}

const KEY = "mentor.token";

export const localTokenStorage: TokenStorage = {
  async get() {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  async set(token) {
    try {
      localStorage.setItem(KEY, token);
    } catch {
      /* private mode: the session just won't persist */
    }
  },
  async clear() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  },
};
