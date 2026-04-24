import { pokerogueApi } from "#api/pokerogue-api";
import { buildBypassUserInfo } from "#app/tempaitown-host";
import { bypassLogin } from "#constants/app-constants";
import type { UserInfo } from "#types/api";
import { randomString } from "#utils/common";

export let loggedInUser: UserInfo | null = null;
// This is a random string that is used to identify the client session - unique per session (tab or window) so that the game will only save on the one that the server is expecting
export const clientSessionId = randomString(32);

export function isLocalProfileMode(): boolean {
  return bypassLogin || (loggedInUser?.profileSource ? loggedInUser.profileSource !== "server" : loggedInUser?.isAuthenticated === false);
}

export function canLogOutCurrentProfile(): boolean {
  return loggedInUser?.profileSource === "aura" || loggedInUser?.profileSource === "server";
}

export async function hydrateLocalUserInfo(): Promise<UserInfo> {
  loggedInUser = await buildBypassUserInfo();
  let lastSessionSlot = -1;
  for (let s = 0; s < 5; s++) {
    if (localStorage.getItem(`sessionData${s || ""}_${loggedInUser.username}`)) {
      lastSessionSlot = s;
      break;
    }
  }
  loggedInUser.lastSessionSlot = lastSessionSlot;

  // Migrate old data from before the username was appended.
  ["data", "sessionData", "sessionData1", "sessionData2", "sessionData3", "sessionData4"].forEach(d => {
    const lsItem = localStorage.getItem(d);
    if (lsItem && !!loggedInUser?.username) {
      const lsUserItem = localStorage.getItem(`${d}_${loggedInUser.username}`);
      if (lsUserItem) {
        localStorage.setItem(`${d}_${loggedInUser.username}_bak`, lsUserItem);
      }
      localStorage.setItem(`${d}_${loggedInUser.username}`, lsItem);
      localStorage.removeItem(d);
    }
  });

  return loggedInUser;
}

export async function updateUserInfo(): Promise<[success: boolean, status: number]> {
  if (!bypassLogin) {
    const [accountInfo, status] = await pokerogueApi.account.getInfo();
    if (!accountInfo) {
      return [false, status];
    }
    loggedInUser = { ...accountInfo, profileSource: "server" };
    return [true, 200];
  }

  await hydrateLocalUserInfo();
  return [true, 200];
}
