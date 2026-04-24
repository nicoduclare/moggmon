import type { BattleScene } from "#app/battle-scene";
import { getEvolutions } from "#balance/pokemon-evolutions";
import { isDev } from "#constants/app-constants";
import { GENERATED_ROSTER_DEXES } from "#constants/generated-roster";
import { getCachedUrl } from "#utils/fetch-utils";
import { getPokemonSpecies } from "#utils/pokemon-utils";

const CANONICAL_ENABLE_PARAM = "pokedex";
const ENABLE_PARAMS = [CANONICAL_ENABLE_PARAM, "pokedexLab", "archiveLab"];
const DEX_PARAM = "dex";
const QUERY_PARAM = "q";
const FAMILY_ONLY_PARAM = "familyOnly";
const DEBUG_ROUTE_PARAMS = [
  ...ENABLE_PARAMS,
  "battleLab",
  "moveLab",
  "spriteLab",
  "evolutionLab",
  "itemLab",
  "dex",
  "playerDex",
  "enemyDex",
  "playerMoves",
  "move",
  "q",
  "page",
  "frame",
  "familyOnly",
  "debugUi",
  "playerPolicy",
];

type ArchiveLabState = {
  dex: number;
  query: string;
  familyOnly: boolean;
};

function parseArchiveLabState(): ArchiveLabState | null {
  if (!isDev) {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  if (!ENABLE_PARAMS.some(param => params.get(param) === "1")) {
    return null;
  }

  const rawDex = Number.parseInt(params.get(DEX_PARAM) || `${GENERATED_ROSTER_DEXES[0]}`, 10);
  const dex = GENERATED_ROSTER_DEXES.includes(rawDex) ? rawDex : GENERATED_ROSTER_DEXES[0];
  const query = (params.get(QUERY_PARAM) || "").trim();
  const familyOnly = params.get(FAMILY_ONLY_PARAM) === "1";

  return { dex, query, familyOnly };
}

function writeArchiveLabState(state: ArchiveLabState): void {
  const url = new URL(window.location.href);
  url.searchParams.set(CANONICAL_ENABLE_PARAM, "1");
  for (const param of ENABLE_PARAMS) {
    if (param !== CANONICAL_ENABLE_PARAM) {
      url.searchParams.delete(param);
    }
  }
  url.searchParams.set(DEX_PARAM, String(state.dex));
  if (state.query) {
    url.searchParams.set(QUERY_PARAM, state.query);
  } else {
    url.searchParams.delete(QUERY_PARAM);
  }
  if (state.familyOnly) {
    url.searchParams.set(FAMILY_ONLY_PARAM, "1");
  } else {
    url.searchParams.delete(FAMILY_ONLY_PARAM);
  }
  window.history.replaceState({}, "", url);
}

function clearDebugRouteParams(url: URL): void {
  for (const key of DEBUG_ROUTE_PARAMS) {
    url.searchParams.delete(key);
  }
}

function textStyle(fontSize: string, color = "#f7f7f7"): Phaser.Types.GameObjects.Text.TextStyle {
  return {
    fontFamily: "emerald",
    fontSize,
    color,
  };
}

function getFamilyDexes(dex: number): number[] {
  const species = getPokemonSpecies(dex);
  const rootDex = species.getRootSpeciesId();
  return Array.from(new Set([rootDex, ...getEvolutions(rootDex).values()]));
}

function getFamilyLabel(dex: number): string {
  const familyDexes = getFamilyDexes(dex);
  return familyDexes.map(memberDex => `#${memberDex}`).join(" · ");
}

function resolveEnemyDex(dex: number): number {
  const sourceRoot = getPokemonSpecies(dex).getRootSpeciesId();
  const nextDex = GENERATED_ROSTER_DEXES.find(
    candidateDex => getPokemonSpecies(candidateDex).getRootSpeciesId() !== sourceRoot,
  );
  return nextDex ?? dex;
}

function matchesQuery(dex: number, query: string): boolean {
  if (!query) {
    return true;
  }

  const normalized = query.trim().toLowerCase();
  const species = getPokemonSpecies(dex);
  return species.name.toLowerCase().includes(normalized) || `${dex}`.includes(normalized);
}

class ArchiveLab {
  private readonly scene: BattleScene;
  private state: ArchiveLabState;
  private readonly root: Phaser.GameObjects.Container;
  private readonly subtitleText: Phaser.GameObjects.Text;
  private readonly statusText: Phaser.GameObjects.Text;
  private readonly controlsRoot: HTMLDivElement;
  private readonly panelRoot: HTMLDivElement;
  private readonly detailRoot: HTMLDivElement;
  private readonly gridRoot: HTMLDivElement;
  private readonly keyboardHandler: (event: KeyboardEvent) => void;
  private dexInput: HTMLInputElement | null = null;
  private searchInput: HTMLInputElement | null = null;

  constructor(scene: BattleScene, state: ArchiveLabState) {
    this.scene = scene;
    this.state = state;

    const width = Number(scene.scale.width) || 1920;
    const height = Number(scene.scale.height) || 1080;

    this.root = scene.add.container(0, 0).setDepth(1000);
    this.root.add([
      scene.add.rectangle(0, 0, width, height, 0x10141c, 0.98).setOrigin(0),
      scene.add.text(48, 28, "Mogger Mon Archive Lab", textStyle("46px")),
      scene.add.text(48, 82, "", textStyle("22px", "#9db4c8")),
      scene.add.text(48, height - 42, "", textStyle("20px", "#9ad1ff")),
    ]);

    this.subtitleText = this.root.list[2] as Phaser.GameObjects.Text;
    this.statusText = this.root.list[3] as Phaser.GameObjects.Text;

    this.controlsRoot = this.createControls();
    this.panelRoot = this.createPanelRoot();
    this.detailRoot = this.createDetailRoot();
    this.gridRoot = this.createGridRoot();
    this.panelRoot.append(this.detailRoot, this.gridRoot);
    this.keyboardHandler = event => this.handleKeyboardNavigation(event);
    document.addEventListener("keydown", this.keyboardHandler);
    scene.events.once(Phaser.Scenes.Events.DESTROY, () => this.destroy());
  }

  async start(): Promise<void> {
    this.render();
  }

  private createControls(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "archive-lab-controls";
    Object.assign(root.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      zIndex: "9999",
      display: "flex",
      gap: "8px",
      alignItems: "center",
      padding: "10px 12px",
      borderRadius: "12px",
      background: "rgba(12, 15, 20, 0.92)",
      border: "1px solid rgba(255,255,255,0.12)",
      fontFamily: "monospace",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);

    const label = document.createElement("span");
    label.textContent = "Dex";
    root.append(label);

    const input = document.createElement("input");
    input.type = "number";
    input.min = String(GENERATED_ROSTER_DEXES[0]);
    input.max = String(GENERATED_ROSTER_DEXES.at(-1) ?? GENERATED_ROSTER_DEXES[0]);
    input.value = String(this.state.dex);
    input.dataset.testid = "archive-lab-dex-input";
    this.dexInput = input;
    Object.assign(input.style, {
      width: "72px",
      padding: "6px 8px",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(input);

    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Search name or dex";
    searchInput.value = this.state.query;
    searchInput.dataset.testid = "archive-lab-search-input";
    this.searchInput = searchInput;
    Object.assign(searchInput.style, {
      width: "220px",
      padding: "6px 8px",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(searchInput);

    const attachButton = (labelText: string, handler: () => void, testId: string) => {
      const button = document.createElement("button");
      button.textContent = labelText;
      button.dataset.testid = testId;
      Object.assign(button.style, {
        padding: "6px 10px",
        borderRadius: "8px",
        border: "1px solid rgba(255,255,255,0.18)",
        background: "rgba(255,255,255,0.08)",
        color: "#f7f7f7",
        cursor: "pointer",
      } satisfies Partial<CSSStyleDeclaration>);
      button.onclick = handler;
      root.append(button);
    };

    const openRoute = (params: Record<string, string>) => {
      const url = new URL(window.location.href);
      clearDebugRouteParams(url);
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
      window.location.assign(url.toString());
    };

    attachButton("Prev", () => this.selectRelativeDex(-1), "archive-lab-prev");
    attachButton("Next", () => this.selectRelativeDex(1), "archive-lab-next");
    attachButton(
      "Toggle Family",
      () => this.setState({ familyOnly: !this.state.familyOnly }),
      "archive-lab-family-only",
    );
    attachButton("Sprite", () => openRoute({ spriteLab: "1", dex: String(this.state.dex) }), "archive-lab-sprite");
    attachButton("Maxx", () => openRoute({ evolutionLab: "1", dex: String(this.state.dex) }), "archive-lab-mutation");
    attachButton("Items", () => openRoute({ itemLab: "1" }), "archive-lab-items");
    attachButton(
      "Battle",
      () =>
        openRoute({
          battleLab: "1",
          playerDex: String(this.state.dex),
          enemyDex: String(resolveEnemyDex(this.state.dex)),
          debugUi: "0",
        }),
      "archive-lab-battle",
    );
    attachButton(
      "Move",
      () =>
        openRoute({
          moveLab: "1",
          playerDex: String(this.state.dex),
          enemyDex: String(resolveEnemyDex(this.state.dex)),
          move: "GROWL",
          playerPolicy: "first",
          debugUi: "1",
        }),
      "archive-lab-move",
    );
    attachButton(
      "Go",
      () => this.setDex(Number.parseInt(input.value || `${GENERATED_ROSTER_DEXES[0]}`, 10)),
      "archive-lab-go",
    );

    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        this.setDex(Number.parseInt(input.value || `${GENERATED_ROSTER_DEXES[0]}`, 10));
      }
    });
    searchInput.addEventListener("input", () => this.setState({ query: searchInput.value.trim() }));

    document.body.append(root);
    return root;
  }

  private setState(patch: Partial<ArchiveLabState>): void {
    this.state = {
      ...this.state,
      ...patch,
    };
    if (this.dexInput) {
      this.dexInput.value = String(this.state.dex);
    }
    if (this.searchInput) {
      this.searchInput.value = this.state.query;
    }
    writeArchiveLabState(this.state);
    this.render();
  }

  private setDex(dex: number): void {
    const firstDex = GENERATED_ROSTER_DEXES[0];
    const lastDex = GENERATED_ROSTER_DEXES.at(-1) ?? firstDex;
    const clampedDex = Math.max(firstDex, Math.min(dex, lastDex));
    const resolvedDex = GENERATED_ROSTER_DEXES.includes(clampedDex)
      ? clampedDex
      : (GENERATED_ROSTER_DEXES.find(candidateDex => candidateDex >= clampedDex) ?? lastDex);
    this.setState({ dex: resolvedDex });
  }

  private getVisibleDexes(): number[] {
    const familyDexes = getFamilyDexes(this.state.dex);
    return GENERATED_ROSTER_DEXES.filter(dex => {
      if (this.state.familyOnly && !familyDexes.includes(dex)) {
        return false;
      }
      return matchesQuery(dex, this.state.query);
    });
  }

  private selectRelativeDex(offset: number): void {
    const visibleDexes = this.getVisibleDexes();
    if (visibleDexes.length === 0) {
      return;
    }

    let currentIndex = visibleDexes.indexOf(this.state.dex);
    if (currentIndex < 0) {
      currentIndex = visibleDexes.findIndex(dex => dex > this.state.dex);
      if (currentIndex < 0) {
        currentIndex = visibleDexes.length - 1;
      }
    }

    const nextIndex = Math.max(0, Math.min(currentIndex + offset, visibleDexes.length - 1));
    this.setDex(visibleDexes[nextIndex]);
  }

  private handleKeyboardNavigation(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "")) {
      return;
    }

    switch (event.key) {
      case "ArrowUp":
      case "ArrowLeft":
        event.preventDefault();
        this.selectRelativeDex(-1);
        break;
      case "ArrowDown":
      case "ArrowRight":
        event.preventDefault();
        this.selectRelativeDex(1);
        break;
      case "PageUp":
        event.preventDefault();
        this.selectRelativeDex(-12);
        break;
      case "PageDown":
        event.preventDefault();
        this.selectRelativeDex(12);
        break;
      case "Home": {
        const visibleDexes = this.getVisibleDexes();
        if (visibleDexes.length > 0) {
          event.preventDefault();
          this.setDex(visibleDexes[0]);
        }
        break;
      }
      case "End": {
        const visibleDexes = this.getVisibleDexes();
        if (visibleDexes.length > 0) {
          event.preventDefault();
          this.setDex(visibleDexes.at(-1) ?? visibleDexes[0]);
        }
        break;
      }
      case "/":
        event.preventDefault();
        this.searchInput?.focus();
        break;
    }
  }

  private createPanelRoot(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "archive-lab-panel";
    Object.assign(root.style, {
      position: "fixed",
      top: "126px",
      left: "40px",
      right: "40px",
      bottom: "70px",
      zIndex: "9998",
      display: "grid",
      gridTemplateColumns: "360px 1fr",
      gap: "16px",
      alignItems: "stretch",
    } satisfies Partial<CSSStyleDeclaration>);
    document.body.append(root);
    return root;
  }

  private createDetailRoot(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "archive-lab-detail";
    Object.assign(root.style, {
      padding: "20px",
      borderRadius: "18px",
      background: "rgba(10, 14, 20, 0.92)",
      border: "1px solid rgba(255,255,255,0.12)",
      color: "#f7f7f7",
      fontFamily: "monospace",
      overflow: "auto",
    } satisfies Partial<CSSStyleDeclaration>);
    return root;
  }

  private createGridRoot(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "archive-lab-grid";
    Object.assign(root.style, {
      padding: "16px",
      borderRadius: "18px",
      background: "rgba(10, 14, 20, 0.92)",
      border: "1px solid rgba(255,255,255,0.12)",
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(116px, 1fr))",
      gap: "10px",
      alignContent: "start",
      overflowY: "auto",
    } satisfies Partial<CSSStyleDeclaration>);
    return root;
  }

  private render(): void {
    const totalFamilies = new Set(GENERATED_ROSTER_DEXES.map(dex => getPokemonSpecies(dex).getRootSpeciesId())).size;
    const species = getPokemonSpecies(this.state.dex);
    const familyDexes = getFamilyDexes(this.state.dex);
    const visibleDexes = this.getVisibleDexes();

    this.subtitleText.setText(`${GENERATED_ROSTER_DEXES.length} generated entries · ${totalFamilies} families`);
    this.statusText.setText(
      `Archive ready · selected dex ${this.state.dex} · family ${getFamilyLabel(this.state.dex)} · showing ${visibleDexes.length}`,
    );

    this.detailRoot.innerHTML = "";
    const hero = document.createElement("div");
    hero.innerHTML = `
      <div style="display:grid;gap:18px;">
        <div style="display:flex;gap:16px;align-items:flex-start;">
          <img src="${getCachedUrl(`./images/pokemon/icons/1/${this.state.dex}.png`)}" alt="${species.name}" style="width:112px;height:112px;image-rendering:pixelated;border-radius:24px;background:linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));padding:12px;border:1px solid rgba(255,255,255,0.08);box-shadow:0 12px 32px rgba(0,0,0,0.28);" />
          <div style="display:grid;gap:8px;min-width:0;">
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
              <div style="font-size:30px;color:#f7f7f7;">${species.name}</div>
              <div style="padding:4px 10px;border-radius:999px;background:rgba(141,199,255,0.14);border:1px solid rgba(141,199,255,0.24);font-size:12px;color:#a7dbff;">dex #${this.state.dex}</div>
            </div>
            <div style="display:grid;gap:6px;font-size:14px;color:#9db4c8;">
              <div>root #${species.getRootSpeciesId()}</div>
              <div>family ${getFamilyLabel(this.state.dex)}</div>
              <div>${this.state.familyOnly ? "family focus on" : "full roster view"}${this.state.query ? ` · query “${this.state.query}”` : ""}</div>
            </div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;">
          <div style="padding:12px 14px;border-radius:14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">
            <div style="font-size:11px;color:#8dc7ff;letter-spacing:0.08em;text-transform:uppercase;">Roster</div>
            <div style="font-size:24px;color:#f7f7f7;margin-top:4px;">${GENERATED_ROSTER_DEXES.length}</div>
          </div>
          <div style="padding:12px 14px;border-radius:14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">
            <div style="font-size:11px;color:#8dc7ff;letter-spacing:0.08em;text-transform:uppercase;">Families</div>
            <div style="font-size:24px;color:#f7f7f7;margin-top:4px;">${totalFamilies}</div>
          </div>
          <div style="padding:12px 14px;border-radius:14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);">
            <div style="font-size:11px;color:#8dc7ff;letter-spacing:0.08em;text-transform:uppercase;">Visible</div>
            <div style="font-size:24px;color:#f7f7f7;margin-top:4px;">${visibleDexes.length}</div>
          </div>
        </div>
      </div>
      <div style="margin-top:18px;font-size:13px;line-height:1.5;color:#cfd9e6;">
        Archive Lab is the generated-roster showcase view. It tracks every generated entry we currently ship, then links straight into Sprite Lab, Maxx Lab, and live Battle Lab for the selected mon. Scroll the grid, click a card, or use arrow keys/PageUp/PageDown to browse.
      </div>
    `;
    this.detailRoot.append(hero);

    const actions = document.createElement("div");
    Object.assign(actions.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "8px",
      marginTop: "18px",
      marginBottom: "18px",
    } satisfies Partial<CSSStyleDeclaration>);

    const makeAction = (label: string, handler: () => void) => {
      const button = document.createElement("button");
      button.textContent = label;
      Object.assign(button.style, {
        padding: "8px 12px",
        borderRadius: "10px",
        border: "1px solid rgba(255,255,255,0.16)",
        background: "rgba(255,255,255,0.08)",
        color: "#f7f7f7",
        fontFamily: "monospace",
        cursor: "pointer",
      } satisfies Partial<CSSStyleDeclaration>);
      button.onclick = handler;
      actions.append(button);
    };

    const goTo = (params: Record<string, string>) => {
      const url = new URL(window.location.href);
      clearDebugRouteParams(url);
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
      window.location.assign(url.toString());
    };

    makeAction("Open Sprite Lab", () => goTo({ spriteLab: "1", dex: String(this.state.dex) }));
    makeAction("Open Maxx Lab", () => goTo({ evolutionLab: "1", dex: String(this.state.dex) }));
    makeAction("Open Item Lab", () => goTo({ itemLab: "1" }));
    makeAction("Open Battle Lab", () =>
      goTo({
        battleLab: "1",
        playerDex: String(this.state.dex),
        enemyDex: String(resolveEnemyDex(this.state.dex)),
        debugUi: "0",
      }),
    );
    makeAction("Open Move Lab", () =>
      goTo({
        moveLab: "1",
        playerDex: String(this.state.dex),
        enemyDex: String(resolveEnemyDex(this.state.dex)),
        move: "GROWL",
        playerPolicy: "first",
        debugUi: "1",
      }),
    );
    this.detailRoot.append(actions);

    const familyHeading = document.createElement("div");
    familyHeading.textContent = "Lineage";
    Object.assign(familyHeading.style, {
      fontSize: "16px",
      color: "#8dc7ff",
      marginBottom: "10px",
    } satisfies Partial<CSSStyleDeclaration>);
    this.detailRoot.append(familyHeading);

    const familyRow = document.createElement("div");
    Object.assign(familyRow.style, {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))",
      gap: "10px",
      marginBottom: "18px",
    } satisfies Partial<CSSStyleDeclaration>);
    for (const familyDex of familyDexes) {
      const button = document.createElement("button");
      Object.assign(button.style, {
        display: "grid",
        gap: "8px",
        justifyItems: "center",
        padding: "10px 8px",
        borderRadius: "14px",
        border: `1px solid ${familyDex === this.state.dex ? "rgba(127,240,181,0.6)" : "rgba(255,255,255,0.14)"}`,
        background: familyDex === this.state.dex ? "rgba(127,240,181,0.18)" : "rgba(255,255,255,0.05)",
        color: "#f7f7f7",
        fontFamily: "monospace",
        cursor: "pointer",
      } satisfies Partial<CSSStyleDeclaration>);
      button.innerHTML = `
        <img src="${getCachedUrl(`./images/pokemon/icons/1/${familyDex}.png`)}" alt="${getPokemonSpecies(familyDex).name}" style="width:46px;height:46px;image-rendering:pixelated;" />
        <div style="font-size:11px;color:#9db4c8;">#${familyDex}</div>
        <div style="font-size:11px;line-height:1.3;">${getPokemonSpecies(familyDex).name}</div>
      `;
      button.onclick = () => {
        this.state = { ...this.state, dex: familyDex };
        writeArchiveLabState(this.state);
        this.render();
      };
      familyRow.append(button);
    }
    this.detailRoot.append(familyRow);

    const gridFragment = document.createDocumentFragment();
    this.gridRoot.innerHTML = "";
    for (const dex of visibleDexes) {
      const candidateSpecies = getPokemonSpecies(dex);
      const card = document.createElement("button");
      card.dataset.testid = `archive-lab-card-${dex}`;
      Object.assign(card.style, {
        display: "grid",
        gap: "8px",
        justifyItems: "center",
        padding: "12px 8px",
        borderRadius: "14px",
        border: `1px solid ${dex === this.state.dex ? "rgba(127,240,181,0.7)" : "rgba(255,255,255,0.10)"}`,
        background: dex === this.state.dex ? "rgba(127,240,181,0.12)" : "rgba(255,255,255,0.04)",
        color: "#f7f7f7",
        cursor: "pointer",
        fontFamily: "monospace",
        textAlign: "center",
      } satisfies Partial<CSSStyleDeclaration>);
      card.innerHTML = `
        <img src="${getCachedUrl(`./images/pokemon/icons/1/${dex}.png`)}" alt="${candidateSpecies.name}" style="width:48px;height:48px;image-rendering:pixelated;" />
        <div style="font-size:12px;color:#9db4c8;">#${dex}</div>
        <div style="font-size:12px;line-height:1.3;">${candidateSpecies.name}</div>
        <div style="font-size:10px;color:#7c93aa;">root #${candidateSpecies.getRootSpeciesId()}</div>
      `;
      card.onclick = () => {
        this.setDex(dex);
      };
      gridFragment.append(card);
    }
    this.gridRoot.append(gridFragment);
    this.gridRoot.querySelector<HTMLElement>(`[data-testid="archive-lab-card-${this.state.dex}"]`)?.scrollIntoView({
      block: "nearest",
    });
  }

  destroy(): void {
    document.removeEventListener("keydown", this.keyboardHandler);
    this.controlsRoot.remove();
    this.panelRoot.remove();
    this.root.destroy(true);
  }
}

export async function maybeStartArchiveLab(scene: BattleScene): Promise<boolean> {
  const state = parseArchiveLabState();
  if (!state) {
    return false;
  }

  writeArchiveLabState(state);
  const lab = new ArchiveLab(scene, state);
  await lab.start();
  return true;
}
