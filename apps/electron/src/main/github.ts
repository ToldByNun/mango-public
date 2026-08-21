import { net, shell } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { app } from "electron";

const CLIENT_ID = "Ov23liYourClientId"; // Replace with your GitHub OAuth App client ID
const SCOPES = "repo,read:user";

type GithubUser = { login: string; avatar_url: string; name: string | null };
type StoredAuth = { token: string; user: GithubUser };

function authPath(): string {
  const dir = join(app.getPath("userData"), "auth");
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return join(dir, "github.json");
}

export function getStoredAuth(): StoredAuth | null {
  const p = authPath();
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function storeAuth(auth: StoredAuth): void {
  writeFileSync(authPath(), JSON.stringify(auth));
}

export function clearAuth(): void {
  const p = authPath();
  if (existsSync(p)) writeFileSync(p, "");
}

async function fetchJson<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const resp = await net.fetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...((opts.headers as Record<string, string>) ?? {}) },
  });
  return resp.json() as Promise<T>;
}

type DeviceCodeResponse = {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
};

type TokenResponse = {
  access_token?: string;
  token_type?: string;
  error?: string;
};

export async function startDeviceFlow(): Promise<{ userCode: string; verificationUri: string; poll: () => Promise<StoredAuth | null> } | null> {
  let dcr: DeviceCodeResponse;
  try {
    dcr = await fetchJson<DeviceCodeResponse>("https://github.com/login/device/code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: CLIENT_ID, scope: SCOPES }),
    });
  } catch (err) {
    console.error("GitHub device flow failed:", err);
    return null;
  }

  if (!dcr.device_code || !dcr.user_code) {
    console.error("GitHub device flow: invalid response", dcr);
    return null;
  }

  void shell.openExternal(dcr.verification_uri);

  const poll = async (): Promise<StoredAuth | null> => {
    const deadline = Date.now() + dcr.expires_in * 1000;
    const interval = (dcr.interval || 5) * 1000;

    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, interval));
      try {
        const tokenResp = await fetchJson<TokenResponse>("https://github.com/login/oauth/access_token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            client_id: CLIENT_ID,
            device_code: dcr.device_code,
            grant_type: "urn:ietf:params:oauth:grant-type:device_code",
          }),
        });

        if (tokenResp.access_token) {
          const user = await fetchJson<GithubUser>("https://api.github.com/user", {
            headers: { Authorization: `Bearer ${tokenResp.access_token}` },
          });
          const auth: StoredAuth = { token: tokenResp.access_token, user };
          storeAuth(auth);
          return auth;
        }

        if (tokenResp.error === "expired_token" || tokenResp.error === "access_denied") {
          return null;
        }
      } catch {
        return null;
      }
    }
    return null;
  };

  return { userCode: dcr.user_code, verificationUri: dcr.verification_uri, poll };
}

export function getToken(): string | null {
  return getStoredAuth()?.token ?? null;
}
