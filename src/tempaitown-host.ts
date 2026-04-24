import type { UserInfo } from "#types/api";
import { getStoredAuraSession } from "./aura-login";

const GAME_RPC_REQUEST = "tempo.game.rpc";
const GAME_RPC_RESPONSE = "tempo.game.rpc.result";
const GAME_HOST_READY = "tempo.game.host.ready";
const REQUEST_TIMEOUT_MS = 2000;
const DEFAULT_EMBEDDED_GUEST_LABEL = "TempaiTown Guest";

export interface TempaiTownAuthState {
  avatar: string | null;
  displayName: string | null;
  isAuthenticated: boolean;
  username: string | null;
  walletAddress: string | null;
}

export interface TempaiTownWalletState {
  connectedAddress: string | null;
  hasWalletAddressMismatch: boolean;
  isSessionForWallet: boolean;
  sessionAddress: string | null;
  walletAddress: string | null;
}

type TempaiTownHostReadyPayload = {
  auth?: TempaiTownAuthState | null;
  type?: string;
  wallet?: TempaiTownWalletState | null;
};

type TempaiTownRpcResponse = {
  error?: {
    message?: string;
  };
  id?: string;
  result?: unknown;
  type?: string;
};

export interface TempaiTownEmbeddedProfile {
  auth: TempaiTownAuthState;
  displayName: string;
  origin: string;
  saveNamespace: string;
  wallet: TempaiTownWalletState;
}

const DEFAULT_AUTH_STATE: TempaiTownAuthState = Object.freeze({
  avatar: null,
  displayName: null,
  isAuthenticated: false,
  username: null,
  walletAddress: null,
});

const DEFAULT_WALLET_STATE: TempaiTownWalletState = Object.freeze({
  connectedAddress: null,
  hasWalletAddressMismatch: false,
  isSessionForWallet: false,
  sessionAddress: null,
  walletAddress: null,
});

let cachedHostReadyPayload: TempaiTownHostReadyPayload | null = null;
let cachedProfilePromise: Promise<TempaiTownEmbeddedProfile | null> | null = null;
let hostReadyListenerAttached = false;

function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function isEmbeddedInParent(): boolean {
  return isBrowser() && window.parent !== window;
}

function resolveParentOrigin(): string {
  if (typeof document === "undefined") {
    return "*";
  }

  try {
    return document.referrer ? new URL(document.referrer).origin : "*";
  } catch {
    return "*";
  }
}

function shortenAddress(value: unknown): string | null {
  const trimmed = trimString(value);
  if (!/^0x[a-f0-9]{8,}$/i.test(trimmed)) {
    return null;
  }
  return `${trimmed.slice(0, 6)}...${trimmed.slice(-4)}`;
}

function sanitizeStorageSegment(value: unknown): string | null {
  const normalized = trimString(value)
    .toLowerCase()
    .replace(/^0x/, "0x-")
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);

  return normalized || null;
}

function normalizeAuthState(value: unknown): TempaiTownAuthState {
  if (!value || typeof value !== "object") {
    return { ...DEFAULT_AUTH_STATE };
  }

  const record = value as Record<string, unknown>;
  return {
    avatar: trimString(record.avatar) || null,
    displayName: trimString(record.displayName) || null,
    isAuthenticated: Boolean(record.isAuthenticated),
    username: trimString(record.username) || null,
    walletAddress: trimString(record.walletAddress) || null,
  };
}

function normalizeWalletState(value: unknown): TempaiTownWalletState {
  if (!value || typeof value !== "object") {
    return { ...DEFAULT_WALLET_STATE };
  }

  const record = value as Record<string, unknown>;
  return {
    connectedAddress: trimString(record.connectedAddress) || null,
    hasWalletAddressMismatch: Boolean(record.hasWalletAddressMismatch),
    isSessionForWallet: Boolean(record.isSessionForWallet),
    sessionAddress: trimString(record.sessionAddress) || null,
    walletAddress: trimString(record.walletAddress) || null,
  };
}

function attachHostReadyListener(): void {
  if (!isBrowser() || hostReadyListenerAttached) {
    return;
  }

  hostReadyListenerAttached = true;
  window.addEventListener("message", event => {
    const data = event.data as TempaiTownHostReadyPayload | null;
    if (!data || typeof data !== "object" || data.type !== GAME_HOST_READY) {
      return;
    }

    cachedHostReadyPayload = {
      auth: normalizeAuthState(data.auth),
      type: GAME_HOST_READY,
      wallet: normalizeWalletState(data.wallet),
    };
  });
}

async function requestParentRpc<T>(method: string): Promise<T> {
  if (!isEmbeddedInParent()) {
    throw new Error("Not running inside a parent frame");
  }

  const targetOrigin = resolveParentOrigin();
  attachHostReadyListener();

  return await new Promise<T>((resolve, reject) => {
    const requestId = `moggermon-${method}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    const cleanup = () => {
      window.clearTimeout(timeoutId);
      window.removeEventListener("message", onMessage);
    };

    const onMessage = (event: MessageEvent) => {
      if (targetOrigin !== "*" && event.origin !== targetOrigin) {
        return;
      }

      const data = event.data as TempaiTownRpcResponse | null;
      if (!data || typeof data !== "object" || data.type !== GAME_RPC_RESPONSE || data.id !== requestId) {
        return;
      }

      cleanup();

      if (data.error?.message) {
        reject(new Error(data.error.message));
        return;
      }

      resolve(data.result as T);
    };

    const timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error(`Timed out waiting for ${method}`));
    }, REQUEST_TIMEOUT_MS);

    window.addEventListener("message", onMessage);
    window.parent.postMessage(
      {
        id: requestId,
        method,
        type: GAME_RPC_REQUEST,
      },
      targetOrigin,
    );
  });
}

function buildEmbeddedProfile(
  auth: TempaiTownAuthState,
  wallet: TempaiTownWalletState,
  origin: string,
): TempaiTownEmbeddedProfile {
  const stableIdentity =
    sanitizeStorageSegment(auth.username)
    || sanitizeStorageSegment(auth.walletAddress)
    || sanitizeStorageSegment(wallet.sessionAddress)
    || sanitizeStorageSegment(wallet.walletAddress)
    || sanitizeStorageSegment(wallet.connectedAddress)
    || "guest";

  const displayName =
    auth.displayName
    || auth.username
    || shortenAddress(auth.walletAddress)
    || shortenAddress(wallet.walletAddress)
    || shortenAddress(wallet.connectedAddress)
    || DEFAULT_EMBEDDED_GUEST_LABEL;

  return {
    auth,
    displayName,
    origin,
    saveNamespace: `tempaitown_${stableIdentity}`,
    wallet,
  };
}

export function primeTempaiTownHostBridge(): void {
  attachHostReadyListener();
}

export async function getTempaiTownEmbeddedProfile(): Promise<TempaiTownEmbeddedProfile | null> {
  if (!isEmbeddedInParent()) {
    return null;
  }

  if (!cachedProfilePromise) {
    cachedProfilePromise = (async () => {
      attachHostReadyListener();

      const targetOrigin = resolveParentOrigin();
      const cachedAuth = cachedHostReadyPayload?.auth;
      const cachedWallet = cachedHostReadyPayload?.wallet;

      if (cachedAuth && cachedWallet) {
        return buildEmbeddedProfile(cachedAuth, cachedWallet, targetOrigin);
      }

      try {
        const [auth, wallet] = await Promise.all([
          requestParentRpc<TempaiTownAuthState>("auth.get").then(normalizeAuthState),
          requestParentRpc<TempaiTownWalletState>("wallet.get").then(normalizeWalletState),
        ]);
        return buildEmbeddedProfile(auth, wallet, targetOrigin);
      } catch {
        return null;
      }
    })();
  }

  return await cachedProfilePromise;
}

export function resetTempaiTownEmbeddedProfile(): void {
  cachedProfilePromise = null;
}

export async function buildBypassUserInfo(): Promise<UserInfo> {
  const embeddedProfile = await getTempaiTownEmbeddedProfile();
  if (embeddedProfile) {
    const walletAddress =
      embeddedProfile.auth.walletAddress
      || embeddedProfile.wallet.walletAddress
      || embeddedProfile.wallet.connectedAddress
      || null;

    return {
      username: embeddedProfile.saveNamespace,
      lastSessionSlot: -1,
      discordId: "",
      googleId: "",
      hasAdminRole: false,
      displayName: embeddedProfile.displayName,
      avatar: embeddedProfile.auth.avatar,
      walletAddress,
      isAuthenticated: embeddedProfile.auth.isAuthenticated,
      profileSource: "tempaitown",
    };
  }

  const auraSession = getStoredAuraSession();
  if (auraSession) {
    const stableIdentity =
      sanitizeStorageSegment(auraSession.user?.username)
      || sanitizeStorageSegment(auraSession.walletAddress)
      || sanitizeStorageSegment(auraSession.user?.id)
      || "guest";

    const displayName =
      auraSession.user?.displayName
      || auraSession.user?.username
      || shortenAddress(auraSession.walletAddress)
      || "Aura User";

    return {
      username: `aura_${stableIdentity}`,
      lastSessionSlot: -1,
      discordId: "",
      googleId: "",
      hasAdminRole: false,
      displayName,
      avatar: auraSession.user?.avatar || null,
      walletAddress: auraSession.walletAddress || null,
      isAuthenticated: Boolean(auraSession.authenticated ?? true),
      profileSource: "aura",
    };
  }

  return {
    username: "Guest",
    lastSessionSlot: -1,
    discordId: "",
    googleId: "",
    hasAdminRole: false,
    displayName: "Guest",
    avatar: null,
    walletAddress: null,
    isAuthenticated: false,
    profileSource: "guest",
  };
}
