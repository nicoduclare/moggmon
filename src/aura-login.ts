const AURA_SESSION_STORAGE_KEY = "moggermon.aura.session.v1";
const LEGACY_AURA_SESSION_STORAGE_KEY = "mogmon.aura.session.v1";
const DEFAULT_AURA_CLIENT_ID = "moggermon";
const DEFAULT_AURA_LOGIN_ORIGIN = "https://auramaxx.gg";
const AURA_LOGIN_RESULT_MESSAGE_TYPE = "aura.login.result";

type AuraLoginUser = {
  avatar?: string | null;
  displayName?: string | null;
  id?: string | null;
  username?: string | null;
};

export type AuraLoginResult = {
  authenticated?: boolean;
  clientId?: string;
  user?: AuraLoginUser | null;
  walletAddress?: string | null;
};

type AuraSignInOptions = {
  allowGuest?: boolean;
  mode?: "dark" | "light" | "system";
};

type AuraSdk = {
  getSession?: () => AuraLoginResult | null;
  signIn?: (options: Record<string, unknown>) => Promise<AuraLoginResult>;
};

type AuraLoginError = Error & {
  code?: string;
};

declare global {
  interface Window {
    Aura?: AuraSdk;
  }
}

let sdkLoadPromise: Promise<void> | null = null;

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeAuraLoginOrigin(value: string | undefined): string {
  const input = trimString(value) || DEFAULT_AURA_LOGIN_ORIGIN;

  try {
    return new URL(input).origin;
  } catch {
    return DEFAULT_AURA_LOGIN_ORIGIN;
  }
}

function isLoopbackOrigin(origin: string): boolean {
  try {
    const hostname = new URL(origin).hostname;
    return (
      hostname === "localhost"
      || hostname === "127.0.0.1"
      || hostname === "0.0.0.0"
      || hostname === "[::1]"
      || hostname === "::1"
    );
  } catch {
    return false;
  }
}

function shouldUseDirectAuraIframe(origin: string): boolean {
  if (isLoopbackOrigin(origin)) {
    return true;
  }

  try {
    const url = new URL(origin);
    return Boolean(import.meta.env.DEV && url.protocol === "http:");
  } catch {
    return false;
  }
}

function createAuraLoginError(code: string, message: string): AuraLoginError {
  const error = new Error(message) as AuraLoginError;
  error.code = code;
  return error;
}

function normalizeAuraSession(value: unknown): AuraLoginResult | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const record = value as Record<string, unknown>;
  const userRecord = record.user && typeof record.user === "object" ? (record.user as Record<string, unknown>) : null;

  const walletAddress = trimString(record.walletAddress) || null;
  const username = trimString(userRecord?.username) || null;
  const displayName = trimString(userRecord?.displayName) || null;
  const avatar = trimString(userRecord?.avatar) || null;
  const id = trimString(userRecord?.id) || null;
  const clientId = trimString(record.clientId) || resolveAuraClientId();

  if (!walletAddress && !username && !displayName && !id) {
    return null;
  }

  return {
    authenticated: Boolean(record.authenticated ?? true),
    clientId,
    user: {
      avatar,
      displayName,
      id,
      username,
    },
    walletAddress,
  };
}

function persistAuraSession(session: AuraLoginResult | null): void {
  if (!isBrowser()) {
    return;
  }

  if (!session) {
    localStorage.removeItem(AURA_SESSION_STORAGE_KEY);
    return;
  }

  localStorage.setItem(AURA_SESSION_STORAGE_KEY, JSON.stringify(session));
}

function buildAuraSdkUrl(): string {
  return new URL("/login-with-aura/sdk.js", resolveAuraLoginOrigin()).toString();
}

function createAuraState(): string {
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  }

  return `${Date.now()}.${Math.random().toString(36).slice(2)}`;
}

function resolveAuraTheme(mode: AuraSignInOptions["mode"]): "dark" | "light" {
  if (mode === "dark" || mode === "light") {
    return mode;
  }

  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }

  return "light";
}

function buildLocalAuraLoginUrl(options: AuraSignInOptions, state: string): string {
  const url = new URL("/login-with-aura", resolveAuraLoginOrigin());
  const appOrigin = window.location.origin;

  if (!shouldUseDirectAuraIframe(appOrigin)) {
    url.searchParams.set("origin", appOrigin);
  }

  url.searchParams.set("state", state);
  url.searchParams.set("client_id", resolveAuraClientId());
  url.searchParams.set("mode", "iframe");
  url.searchParams.set("theme", resolveAuraTheme(options.mode ?? "system"));

  if (options.allowGuest === false) {
    url.searchParams.set("allow_guest", "0");
  }

  return url.toString();
}

function createLocalAuraOverlay(theme: "dark" | "light"): {
  closeButton: HTMLButtonElement;
  iframe: HTMLIFrameElement;
  overlay: HTMLDivElement;
} {
  const isDark = theme === "dark";
  const overlay = document.createElement("div");
  overlay.style.alignItems = "center";
  overlay.style.background = isDark ? "rgba(0, 0, 0, 0.72)" : "rgba(0, 0, 0, 0.58)";
  overlay.style.boxSizing = "border-box";
  overlay.style.display = "flex";
  overlay.style.inset = "0";
  overlay.style.justifyContent = "center";
  overlay.style.padding = "16px";
  overlay.style.position = "fixed";
  overlay.style.zIndex = "2147483647";

  const frameWrap = document.createElement("div");
  frameWrap.style.background = isDark ? "#050505" : "#ffffff";
  frameWrap.style.border = isDark ? "1px solid rgba(255, 255, 255, 0.2)" : "1px solid rgba(255, 255, 255, 0.26)";
  frameWrap.style.borderRadius = "8px";
  frameWrap.style.boxShadow = "0 24px 80px rgba(0, 0, 0, 0.35)";
  frameWrap.style.height = "min(740px, calc(100vh - 32px))";
  frameWrap.style.maxWidth = "460px";
  frameWrap.style.overflow = "hidden";
  frameWrap.style.position = "relative";
  frameWrap.style.width = "min(460px, calc(100vw - 32px))";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close Login with Aura");
  closeButton.textContent = "x";
  closeButton.style.alignItems = "center";
  closeButton.style.background = isDark ? "rgba(255, 255, 255, 0.88)" : "rgba(0, 0, 0, 0.72)";
  closeButton.style.border = isDark ? "1px solid rgba(0, 0, 0, 0.24)" : "1px solid rgba(255, 255, 255, 0.24)";
  closeButton.style.borderRadius = "999px";
  closeButton.style.color = isDark ? "#111111" : "#ffffff";
  closeButton.style.cursor = "pointer";
  closeButton.style.display = "flex";
  closeButton.style.font = "700 16px/1 system-ui, sans-serif";
  closeButton.style.height = "34px";
  closeButton.style.justifyContent = "center";
  closeButton.style.position = "absolute";
  closeButton.style.right = "10px";
  closeButton.style.top = "10px";
  closeButton.style.width = "34px";
  closeButton.style.zIndex = "2";

  const iframe = document.createElement("iframe");
  iframe.title = "Login with Aura";
  iframe.allow = "publickey-credentials-get *; publickey-credentials-create *; clipboard-read; clipboard-write";
  iframe.style.background = isDark ? "#050505" : "#ffffff";
  iframe.style.border = "0";
  iframe.style.display = "block";
  iframe.style.height = "100%";
  iframe.style.width = "100%";

  frameWrap.append(closeButton, iframe);
  overlay.append(frameWrap);

  return { closeButton, iframe, overlay };
}

async function signInWithLocalAuraIframe(options: AuraSignInOptions = {}): Promise<AuraLoginResult> {
  if (!isBrowser()) {
    throw new Error("Aura login requires a browser environment.");
  }

  return new Promise<AuraLoginResult>((resolve, reject) => {
    const auraOrigin = resolveAuraLoginOrigin();
    const state = createAuraState();
    const theme = resolveAuraTheme(options.mode ?? "system");
    const nodes = createLocalAuraOverlay(theme);
    let settled = false;

    const cleanup = () => {
      window.removeEventListener("message", handleMessage);
      document.removeEventListener("keydown", handleKeydown);
      nodes.overlay.remove();
    };

    const fail = (error: AuraLoginError) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(error);
    };

    const succeed = (payload: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(payload as AuraLoginResult);
    };

    function handleMessage(event: MessageEvent): void {
      if (event.origin !== auraOrigin) {
        return;
      }

      const data = event.data as Record<string, unknown> | null;
      if (!data || data.type !== AURA_LOGIN_RESULT_MESSAGE_TYPE || data.state !== state) {
        return;
      }

      if (data.ok) {
        succeed(data.payload || {});
        return;
      }

      const error = data.error && typeof data.error === "object" ? (data.error as Record<string, unknown>) : null;
      fail(
        createAuraLoginError(
          trimString(error?.code) || "LOGIN_FAILED",
          trimString(error?.message) || "Login with Aura failed.",
        ),
      );
    }

    function handleKeydown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        fail(createAuraLoginError("USER_CLOSED", "Login with Aura was closed."));
      }
    }

    nodes.closeButton.addEventListener("click", () => {
      fail(createAuraLoginError("USER_CLOSED", "Login with Aura was closed."));
    });
    window.addEventListener("message", handleMessage);
    document.addEventListener("keydown", handleKeydown);
    nodes.iframe.src = buildLocalAuraLoginUrl(options, state);
    document.body.appendChild(nodes.overlay);
    nodes.closeButton.focus({ preventScroll: true });
  });
}

async function ensureAuraSdkLoaded(): Promise<AuraSdk> {
  if (!isBrowser()) {
    throw new Error("Aura login requires a browser environment.");
  }

  if (window.Aura?.signIn) {
    return window.Aura;
  }

  if (!sdkLoadPromise) {
    sdkLoadPromise = new Promise<void>((resolve, reject) => {
      const sdkUrl = buildAuraSdkUrl();
      const existingScript = document.querySelector<HTMLScriptElement>(`script[src="${sdkUrl}"]`);
      if (existingScript?.dataset.auraLoaded === "true") {
        resolve();
        return;
      }

      const script = existingScript || document.createElement("script");
      script.src = sdkUrl;
      script.async = true;
      script.dataset.auraOrigin = resolveAuraLoginOrigin();
      script.onload = () => {
        script.dataset.auraLoaded = "true";
        resolve();
      };
      script.onerror = () => {
        sdkLoadPromise = null;
        if (!existingScript) {
          script.remove();
        }
        reject(new Error("Login with Aura SDK could not be loaded."));
      };

      if (!existingScript) {
        document.head.appendChild(script);
      }
    });
  }

  await sdkLoadPromise;

  if (!window.Aura?.signIn) {
    sdkLoadPromise = null;
    throw new Error("Aura SDK loaded without Aura.signIn().");
  }

  return window.Aura;
}

export function resolveAuraLoginOrigin(): string {
  return normalizeAuraLoginOrigin(import.meta.env.VITE_AURA_LOGIN_ORIGIN);
}

export function resolveAuraClientId(): string {
  return trimString(import.meta.env.VITE_AURA_CLIENT_ID) || DEFAULT_AURA_CLIENT_ID;
}

export function getStoredAuraSession(): AuraLoginResult | null {
  if (!isBrowser()) {
    return null;
  }

  try {
    const stored =
      localStorage.getItem(AURA_SESSION_STORAGE_KEY) ?? localStorage.getItem(LEGACY_AURA_SESSION_STORAGE_KEY) ?? "null";
    const session = normalizeAuraSession(JSON.parse(stored));
    if (
      session
      && localStorage.getItem(LEGACY_AURA_SESSION_STORAGE_KEY)
      && !localStorage.getItem(AURA_SESSION_STORAGE_KEY)
    ) {
      persistAuraSession(session);
      localStorage.removeItem(LEGACY_AURA_SESSION_STORAGE_KEY);
    }
    return session;
  } catch {
    localStorage.removeItem(AURA_SESSION_STORAGE_KEY);
    localStorage.removeItem(LEGACY_AURA_SESSION_STORAGE_KEY);
    return null;
  }
}

export function hasStoredAuraSession(): boolean {
  return !!getStoredAuraSession();
}

export function clearStoredAuraSession(): void {
  persistAuraSession(null);
}

export async function signInWithAura(options: AuraSignInOptions = {}): Promise<AuraLoginResult | null> {
  try {
    const result =
      isBrowser() && shouldUseDirectAuraIframe(window.location.origin)
        ? await signInWithLocalAuraIframe({ ...options, allowGuest: options.allowGuest ?? false })
        : await signInWithAuraSdk(options);

    const normalized = normalizeAuraSession(result);
    if (!normalized) {
      throw new Error("Aura login finished without a usable session.");
    }

    persistAuraSession(normalized);
    return normalized;
  } catch (error) {
    const maybeError = error as { code?: string } | null;
    if (maybeError?.code === "USER_CLOSED") {
      return null;
    }

    throw error;
  }
}

async function signInWithAuraSdk(options: AuraSignInOptions = {}): Promise<AuraLoginResult | null> {
  const Aura = await ensureAuraSdkLoaded();

  return (
    (await Aura.signIn?.({
      allowGuest: options.allowGuest ?? false,
      auraOrigin: resolveAuraLoginOrigin(),
      clientId: resolveAuraClientId(),
      mode: options.mode ?? "system",
      theme: options.mode ?? "system",
    }))
    || Aura.getSession?.()
    || null
  );
}
