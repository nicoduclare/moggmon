import { Battle } from "#app/battle";
import type { BattleScene } from "#app/battle-scene";
import { speciesStarterCosts } from "#balance/starters";
import { isDev } from "#constants/app-constants";
import { GENERATED_ROSTER_DEXES } from "#constants/generated-roster";
import { GENERATED_STARTER_SPECIES } from "#constants/generated-starter-species";
import { allMoves, modifierTypes } from "#data/data-lists";
import { Gender } from "#data/gender";
import { AbilityAttr } from "#enums/ability-attr";
import { BattleStyle } from "#enums/battle-style";
import { BattleType } from "#enums/battle-type";
import { BiomeId } from "#enums/biome-id";
import { Command } from "#enums/command";
import { DexAttr } from "#enums/dex-attr";
import { FieldPosition } from "#enums/field-position";
import { MoveCategory } from "#enums/move-category";
import { MoveId } from "#enums/move-id";
import { MoveUseMode } from "#enums/move-use-mode";
import { Nature } from "#enums/nature";
import { PokemonType } from "#enums/pokemon-type";
import { TrainerSlot } from "#enums/trainer-slot";
import { TrainerType } from "#enums/trainer-type";
import { TrainerVariant } from "#enums/trainer-variant";
import { UiMode } from "#enums/ui-mode";
import type { EnemyPokemon, PlayerPokemon, Pokemon } from "#field/pokemon";
import { Trainer } from "#field/trainer";
import type { PersistentModifier } from "#modifiers/modifier";
import { getMoveTargets } from "#moves/move-utils";
import type { ModifierTypeFunc } from "#types/modifier-types";
import type { Starter } from "#types/save-data";
import { getModifierType } from "#utils/modifier-utils";
import { getPokemonSpecies } from "#utils/pokemon-utils";

const ENABLE_PARAM = "battleLab";
const MOVE_LAB_PARAM = "moveLab";
const MOVE_PARAM = "move";
const PLAYER_DEX_PARAM = "playerDex";
const ENEMY_DEX_PARAM = "enemyDex";
const PLAYER_LEVEL_PARAM = "playerLevel";
const ENEMY_LEVEL_PARAM = "enemyLevel";
const PLAYER_MOVES_PARAM = "playerMoves";
const ENEMY_MOVES_PARAM = "enemyMoves";
const PLAYER_ITEM_PARAM = "playerItem";
const PLAYER_ITEMS_PARAM = "playerItems";
const ENEMY_ITEM_PARAM = "enemyItem";
const ENEMY_ITEMS_PARAM = "enemyItems";
const BIOME_PARAM = "biome";
const HIDE_HUD_PARAM = "hideHud";
const DEBUG_UI_PARAM = "debugUi";
const PLAYER_POLICY_PARAM = "playerPolicy";
const STARTER_SELECT_PARAM = "starterSelect";

const DEFAULT_PLAYER_TEAM = [6];
const DEFAULT_ENEMY_TEAM = [3];
const DEFAULT_LEVEL = 42;
const DEFAULT_BIOME = BiomeId.GRASS;
const DEFAULT_HIDE_HUD = false;
const DEFAULT_DEBUG_UI = true;
const DEFAULT_MOVE = MoveId.GROWL;
const MAX_TEAM_SIZE = 6;
const BATTLE_LAB_SPECIES_IDS = [...GENERATED_ROSTER_DEXES];

type BattleLabPlayerPolicy = "manual" | "smart" | "first" | "random" | "cycle";

type BattleLabSideState = {
  dexes: number[];
  levels: number[];
  items: (string | null)[];
  movesets: (MoveId[] | null)[];
};

type BattleLabState = {
  player: BattleLabSideState;
  enemy: BattleLabSideState;
  biome: BiomeId;
  hideHud: boolean;
  debugUi: boolean;
  playerPolicy: BattleLabPlayerPolicy;
  starterSelect: boolean;
  moveLab: boolean;
  selectedMove: MoveId;
};

type MoveChoice = {
  cursor: number;
  moveId: MoveId;
  targets: number[];
  score: number;
};

function normalizeLookupKey(value: string): string {
  return value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

function getMoveLabMoveIds(): MoveId[] {
  return Object.values(MoveId)
    .filter((value): value is MoveId => typeof value === "number" && value !== MoveId.NONE)
    .filter(moveId => !!allMoves[moveId]);
}

function getMoveRouteName(moveId: MoveId): string {
  return MoveId[moveId] ?? String(moveId);
}

function getMoveDisplayName(moveId: MoveId): string {
  return allMoves[moveId]?.name || getMoveRouteName(moveId);
}

function getBiomeRouteName(biomeId: BiomeId): string {
  return (
    Object.entries(BiomeId)
      .find(([, value]) => value === biomeId)?.[0]
      ?.toLowerCase() ?? String(biomeId)
  );
}

function resolveBiomeIdOrFallback(rawValue: string | null, fallback: BiomeId): BiomeId {
  if (!rawValue) {
    return fallback;
  }

  const normalized = normalizeLookupKey(rawValue);
  const namedBiome = BiomeId[normalized as keyof typeof BiomeId];
  if (namedBiome != null) {
    return namedBiome;
  }

  const numericBiome = Number(rawValue);
  if (Number.isInteger(numericBiome) && Object.values(BiomeId).includes(numericBiome as BiomeId)) {
    return numericBiome as BiomeId;
  }

  return fallback;
}

function getMoveCategoryLabel(moveId: MoveId): string {
  const move = allMoves[moveId];
  return move ? (MoveCategory[move.category] ?? "UNKNOWN").toLowerCase() : "unknown";
}

function getMoveTypeLabel(moveId: MoveId): string {
  const move = allMoves[moveId];
  return move ? (PokemonType[move.type] ?? "UNKNOWN").toLowerCase() : "unknown";
}

function parseBoolean(rawValue: string | null, defaultValue: boolean): boolean {
  if (rawValue == null || rawValue === "") {
    return defaultValue;
  }

  const normalized = rawValue.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return defaultValue;
}

function parsePolicy(rawValue: string | null): BattleLabPlayerPolicy {
  switch ((rawValue || "").trim().toLowerCase()) {
    case "manual":
    case "smart":
    case "first":
    case "random":
    case "cycle":
      return rawValue!.trim().toLowerCase() as BattleLabPlayerPolicy;
    default:
      return "manual";
  }
}

function parseDexList(rawValue: string | null, fallback: number[]): number[] {
  if (!rawValue) {
    return [...fallback];
  }

  const values = rawValue
    .split(",")
    .map(value => Number.parseInt(value.trim(), 10))
    .filter(value => Number.isFinite(value) && value > 0)
    .slice(0, MAX_TEAM_SIZE);

  return values.length > 0 ? values : [...fallback];
}

function expandList<T>(values: T[], length: number, fallback: T): T[] {
  if (length <= 0) {
    return [];
  }

  if (values.length === 0) {
    return new Array(length).fill(fallback);
  }

  if (values.length === 1) {
    return new Array(length).fill(values[0]);
  }

  const expanded = values.slice(0, length);
  while (expanded.length < length) {
    expanded.push(expanded.at(-1) ?? fallback);
  }
  return expanded;
}

function parseLevelList(rawValue: string | null, length: number): number[] {
  const parsed = rawValue
    ? rawValue
        .split(",")
        .map(value => Number.parseInt(value.trim(), 10))
        .filter(value => Number.isFinite(value) && value > 0)
    : [];

  return expandList(parsed, length, DEFAULT_LEVEL);
}

function parseItemList(rawValue: string | null, length: number): (string | null)[] {
  if (!rawValue) {
    return new Array(length).fill(null);
  }

  const entries = rawValue.split(",").map(value => value.trim());
  return expandList(entries, length, "").map(entry => {
    if (!entry || ["none", "-", "null"].includes(entry.toLowerCase())) {
      return null;
    }
    return entry;
  });
}

function resolveMoveId(rawValue: string): MoveId {
  const trimmed = rawValue.trim();
  if (/^\d+$/.test(trimmed)) {
    const numericMoveId = Number.parseInt(trimmed, 10);
    if (allMoves[numericMoveId as MoveId]) {
      return numericMoveId as MoveId;
    }
  }

  const normalized = normalizeLookupKey(trimmed);
  const resolved = (MoveId as unknown as Record<string, unknown>)[normalized];
  if (typeof resolved !== "number") {
    const resolvedByDisplayName = getMoveLabMoveIds().find(
      moveId => normalizeLookupKey(getMoveDisplayName(moveId)) === normalized,
    );
    if (resolvedByDisplayName != null) {
      return resolvedByDisplayName;
    }
    throw new Error(`Unknown move "${rawValue}"`);
  }
  return resolved as MoveId;
}

function resolveMoveIdOrFallback(rawValue: string | null, fallback: MoveId): MoveId {
  if (!rawValue) {
    return fallback;
  }

  try {
    return resolveMoveId(rawValue.split(/[;|,]/)[0]);
  } catch {
    return fallback;
  }
}

function parseMovesets(rawValue: string | null, length: number): (MoveId[] | null)[] {
  if (!rawValue) {
    return new Array(length).fill(null);
  }

  const entries = expandList(
    rawValue.split(";").map(value => value.trim()),
    length,
    "",
  );

  return entries.map(entry => {
    if (!entry) {
      return null;
    }

    const moveIds = entry
      .split(/[|,]/)
      .map(value => value.trim())
      .filter(Boolean)
      .slice(0, 4)
      .map(resolveMoveId);

    return moveIds.length > 0 ? moveIds : null;
  });
}

function serializeMovesets(movesets: (MoveId[] | null)[]): string | null {
  const serialized = movesets
    .map(moveset => (moveset != null && moveset.length > 0 ? moveset.map(moveId => MoveId[moveId]).join("|") : ""))
    .join(";");

  return serialized.replace(/;/g, "").length > 0 ? serialized : null;
}

function buildSideState(
  dexes: number[],
  levelValue: string | null,
  itemValue: string | null,
  moveValue: string | null,
): BattleLabSideState {
  return {
    dexes,
    levels: parseLevelList(levelValue, dexes.length),
    items: parseItemList(itemValue, dexes.length),
    movesets: parseMovesets(moveValue, dexes.length),
  };
}

function withMoveLabMove(state: BattleLabState, moveId = state.selectedMove): BattleLabState {
  if (!state.moveLab) {
    return state;
  }

  const movesets = expandList(state.player.movesets, state.player.dexes.length, null);
  if (movesets.length === 0) {
    return { ...state, selectedMove: moveId };
  }

  movesets[0] = [moveId];
  return {
    ...state,
    selectedMove: moveId,
    player: {
      ...state.player,
      movesets,
    },
  };
}

function parseBattleLabState(): BattleLabState | null {
  if (!isDev) {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  const moveLab = params.get(MOVE_LAB_PARAM) === "1";
  if (params.get(ENABLE_PARAM) !== "1" && !moveLab) {
    return null;
  }

  const playerDexes = parseDexList(params.get(PLAYER_DEX_PARAM), DEFAULT_PLAYER_TEAM);
  const enemyDexes = parseDexList(params.get(ENEMY_DEX_PARAM), DEFAULT_ENEMY_TEAM);
  const selectedMove = resolveMoveIdOrFallback(params.get(MOVE_PARAM) ?? params.get(PLAYER_MOVES_PARAM), DEFAULT_MOVE);
  const playerPolicy = params.has(PLAYER_POLICY_PARAM)
    ? parsePolicy(params.get(PLAYER_POLICY_PARAM))
    : moveLab
      ? "first"
      : "manual";

  return withMoveLabMove({
    player: buildSideState(
      playerDexes,
      params.get(PLAYER_LEVEL_PARAM),
      params.get(PLAYER_ITEMS_PARAM) ?? params.get(PLAYER_ITEM_PARAM),
      params.get(PLAYER_MOVES_PARAM) ?? (moveLab ? getMoveRouteName(selectedMove) : null),
    ),
    enemy: buildSideState(
      enemyDexes,
      params.get(ENEMY_LEVEL_PARAM),
      params.get(ENEMY_ITEMS_PARAM) ?? params.get(ENEMY_ITEM_PARAM),
      params.get(ENEMY_MOVES_PARAM),
    ),
    biome: resolveBiomeIdOrFallback(params.get(BIOME_PARAM), DEFAULT_BIOME),
    hideHud: parseBoolean(params.get(HIDE_HUD_PARAM), DEFAULT_HIDE_HUD),
    debugUi: parseBoolean(params.get(DEBUG_UI_PARAM), DEFAULT_DEBUG_UI),
    playerPolicy,
    starterSelect: parseBoolean(params.get(STARTER_SELECT_PARAM), false),
    moveLab,
    selectedMove,
  });
}

function writeBattleLabState(state: BattleLabState): URL {
  const url = new URL(window.location.href);
  if (state.moveLab) {
    url.searchParams.set(MOVE_LAB_PARAM, "1");
    url.searchParams.set(MOVE_PARAM, getMoveRouteName(state.selectedMove));
    url.searchParams.delete(ENABLE_PARAM);
  } else {
    url.searchParams.set(ENABLE_PARAM, "1");
    url.searchParams.delete(MOVE_LAB_PARAM);
    url.searchParams.delete(MOVE_PARAM);
  }
  url.searchParams.set(PLAYER_DEX_PARAM, state.player.dexes.join(","));
  url.searchParams.set(ENEMY_DEX_PARAM, state.enemy.dexes.join(","));
  url.searchParams.set(PLAYER_LEVEL_PARAM, state.player.levels.join(","));
  url.searchParams.set(ENEMY_LEVEL_PARAM, state.enemy.levels.join(","));

  const playerMoves = serializeMovesets(state.player.movesets);
  if (playerMoves) {
    url.searchParams.set(PLAYER_MOVES_PARAM, playerMoves);
  } else {
    url.searchParams.delete(PLAYER_MOVES_PARAM);
  }

  const enemyMoves = serializeMovesets(state.enemy.movesets);
  if (enemyMoves) {
    url.searchParams.set(ENEMY_MOVES_PARAM, enemyMoves);
  } else {
    url.searchParams.delete(ENEMY_MOVES_PARAM);
  }

  const playerItems = state.player.items.some(Boolean) ? state.player.items.map(item => item ?? "").join(",") : null;
  if (playerItems) {
    url.searchParams.set(PLAYER_ITEMS_PARAM, playerItems);
  } else {
    url.searchParams.delete(PLAYER_ITEMS_PARAM);
    url.searchParams.delete(PLAYER_ITEM_PARAM);
  }

  const enemyItems = state.enemy.items.some(Boolean) ? state.enemy.items.map(item => item ?? "").join(",") : null;
  if (enemyItems) {
    url.searchParams.set(ENEMY_ITEMS_PARAM, enemyItems);
  } else {
    url.searchParams.delete(ENEMY_ITEMS_PARAM);
    url.searchParams.delete(ENEMY_ITEM_PARAM);
  }

  url.searchParams.set(BIOME_PARAM, getBiomeRouteName(state.biome));
  url.searchParams.set(HIDE_HUD_PARAM, state.hideHud ? "1" : "0");
  url.searchParams.set(DEBUG_UI_PARAM, state.debugUi ? "1" : "0");
  url.searchParams.set(PLAYER_POLICY_PARAM, state.playerPolicy);
  url.searchParams.set(STARTER_SELECT_PARAM, state.starterSelect ? "1" : "0");
  window.history.replaceState({}, "", url);
  return url;
}

function showBattleLabError(message: string): void {
  const root = document.createElement("div");
  root.dataset.testid = "battle-lab-error";
  Object.assign(root.style, {
    position: "fixed",
    left: "16px",
    top: "16px",
    zIndex: "9999",
    maxWidth: "520px",
    padding: "12px 14px",
    borderRadius: "12px",
    background: "rgba(32, 8, 8, 0.96)",
    border: "1px solid rgba(255, 120, 120, 0.32)",
    color: "#ffd0d0",
    fontFamily: "monospace",
    fontSize: "12px",
    whiteSpace: "pre-wrap",
  } satisfies Partial<CSSStyleDeclaration>);
  root.textContent = `Battle lab failed\n${message}`;
  document.body.append(root);
}

class BattleLab {
  private readonly scene: BattleScene;
  private state: BattleLabState;
  private readonly controlsRoot: HTMLDivElement | null;
  private readonly statusRoot: HTMLDivElement | null;
  private readonly helperToggleRoot: HTMLButtonElement | null;
  private readonly lastMoveCursorByPokemonId = new Map<number, number>();
  private restorePhaseFactory: (() => void) | null = null;
  private statusTimerId: number | null = null;
  private frozenResult: string | null = null;
  private helperUiVisible = true;
  private selectedStarters: Starter[] | null = null;
  private playerInput: HTMLInputElement | null = null;
  private enemyInput: HTMLInputElement | null = null;
  private playerPreviewCanvas: HTMLCanvasElement | null = null;
  private enemyPreviewCanvas: HTMLCanvasElement | null = null;
  private playerPreviewLiveLabel: HTMLDivElement | null = null;
  private enemyPreviewLiveLabel: HTMLDivElement | null = null;
  private playerPreviewPendingLabel: HTMLDivElement | null = null;
  private enemyPreviewPendingLabel: HTMLDivElement | null = null;
  private moveInput: HTMLInputElement | null = null;
  private moveSummaryRoot: HTMLDivElement | null = null;
  private restartingBattle = false;
  private pendingRestartState: BattleLabState | null = null;

  constructor(scene: BattleScene, state: BattleLabState) {
    this.scene = scene;
    this.state = withMoveLabMove(state);
    this.controlsRoot = state.debugUi ? this.createControls() : null;
    this.statusRoot = state.debugUi ? this.createStatus() : null;
    this.helperToggleRoot = state.debugUi ? this.createHelperToggle() : null;
    this.updateHelperUiVisibility();
    scene.events.once(Phaser.Scenes.Events.DESTROY, () => this.destroy());
  }

  async start(): Promise<void> {
    this.scene.reset(false, false, true);
    this.unlockGeneratedStarters();
    this.installPhaseHooks();
    this.hideHud();
    if (this.state.starterSelect) {
      this.renderStatus("Choose recruits in the roster cache...");
      this.openStarterSelect();
      return;
    }

    await this.beginBattle();
  }

  private async beginBattle(): Promise<void> {
    this.renderStatus("Booting live dev battle...");
    if (this.statusTimerId != null) {
      window.clearInterval(this.statusTimerId);
      this.statusTimerId = null;
    }

    try {
      await this.bootBattle();
      this.statusTimerId = window.setInterval(() => this.renderStatus(), 250);
      this.renderStatus();
    } catch (error) {
      console.error("Battle lab boot failed", error);
      const message = error instanceof Error ? error.message : String(error);
      this.renderStatus(`Battle lab failed: ${message}`);
      showBattleLabError(message);
    }
  }

  private openStarterSelect(): void {
    this.setHelperUiVisible(false);
    void this.scene.ui.setMode(
      UiMode.STARTER_SELECT,
      (starters: Starter[]) => {
        this.selectedStarters = starters.slice();
        this.state = this.applySelectedStartersToState(starters);
        writeBattleLabState(this.state);
        void this.scene.ui.setMode(UiMode.MESSAGE).then(() => {
          this.setHelperUiVisible(true);
          void this.beginBattle();
        });
      },
      () => {
        this.state = { ...this.state, starterSelect: false };
        writeBattleLabState(this.state);
        void this.scene.ui.setMode(UiMode.MESSAGE).then(() => {
          this.setHelperUiVisible(true);
          void this.beginBattle();
        });
      },
    );
  }

  private unlockGeneratedStarters(): void {
    const defaultStarterAttr =
      DexAttr.NON_SHINY | DexAttr.MALE | DexAttr.FEMALE | DexAttr.DEFAULT_VARIANT | DexAttr.DEFAULT_FORM;
    const starterRoots = Array.from(
      new Set(
        GENERATED_STARTER_SPECIES.map(speciesId => getPokemonSpecies(speciesId).getRootSpeciesId()).filter(speciesId =>
          Object.hasOwn(speciesStarterCosts, speciesId),
        ),
      ),
    );

    for (const speciesId of starterRoots) {
      const dexEntry = this.scene.gameData.dexData[speciesId];
      const starterData = this.scene.gameData.starterData[speciesId];
      if (!dexEntry || !starterData) {
        continue;
      }

      dexEntry.seenAttr |= defaultStarterAttr;
      dexEntry.caughtAttr |= defaultStarterAttr;
      dexEntry.natureAttr |= 1 << (Nature.HARDY + 1);
      dexEntry.seenCount = Math.max(dexEntry.seenCount, 1);
      dexEntry.caughtCount = Math.max(dexEntry.caughtCount, 1);
      dexEntry.ivs = dexEntry.ivs.map(iv => Math.max(iv, 15));
      starterData.abilityAttr |= AbilityAttr.ABILITY_1;
    }
  }

  private applySelectedStartersToState(starters: Starter[]): BattleLabState {
    const dexes = starters.map(starter => starter.speciesId);
    return withMoveLabMove({
      ...this.state,
      starterSelect: false,
      player: {
        ...this.state.player,
        dexes,
        levels: expandList(this.state.player.levels, dexes.length, DEFAULT_LEVEL),
        items: expandList(this.state.player.items, dexes.length, null),
        movesets: new Array(dexes.length).fill(null),
      },
    });
  }

  private isAutoplayMode(): boolean {
    return this.state.hideHud || this.state.playerPolicy !== "manual";
  }

  private getModeLabel(): string {
    return this.isAutoplayMode() ? `Autoplay:${this.state.playerPolicy}` : "Playable";
  }

  private createControls(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "battle-lab-controls";
    Object.assign(root.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      zIndex: "9999",
      display: "flex",
      flexDirection: "column",
      gap: "10px",
      alignItems: "stretch",
      padding: "10px 12px",
      borderRadius: "12px",
      background: "rgba(12, 15, 20, 0.92)",
      border: "1px solid rgba(255,255,255,0.12)",
      fontFamily: "monospace",
      color: "#f7f7f7",
      minWidth: "360px",
      maxWidth: "440px",
    } satisfies Partial<CSSStyleDeclaration>);

    const createButton = (labelText: string, handler: () => void, testId: string) => {
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
      return button;
    };

    const createInput = (value: string, testId: string) => {
      const input = document.createElement("input");
      input.type = "text";
      input.value = value;
      input.dataset.testid = testId;
      Object.assign(input.style, {
        width: "100%",
        padding: "6px 8px",
        borderRadius: "8px",
        border: "1px solid rgba(255,255,255,0.18)",
        background: "rgba(255,255,255,0.08)",
        color: "#f7f7f7",
      } satisfies Partial<CSSStyleDeclaration>);
      return input;
    };

    const createPreviewCanvas = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 96;
      canvas.height = 96;
      Object.assign(canvas.style, {
        width: "72px",
        height: "72px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.12)",
        imageRendering: "pixelated",
        flexShrink: "0",
      } satisfies Partial<CSSStyleDeclaration>);
      return canvas;
    };

    const sidesRow = document.createElement("div");
    Object.assign(sidesRow.style, {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "10px",
    } satisfies Partial<CSSStyleDeclaration>);

    const getStateFromInputs = (override?: Partial<BattleLabState>): BattleLabState => {
      const playerDexes = parseDexList(this.playerInput?.value ?? "", DEFAULT_PLAYER_TEAM);
      const enemyDexes = parseDexList(this.enemyInput?.value ?? "", DEFAULT_ENEMY_TEAM);

      const nextState: BattleLabState = {
        ...this.state,
        player: {
          ...this.state.player,
          dexes: playerDexes,
          levels: expandList(this.state.player.levels, playerDexes.length, DEFAULT_LEVEL),
          items: expandList(this.state.player.items, playerDexes.length, null),
          movesets: expandList(this.state.player.movesets, playerDexes.length, null),
        },
        enemy: {
          ...this.state.enemy,
          dexes: enemyDexes,
          levels: expandList(this.state.enemy.levels, enemyDexes.length, DEFAULT_LEVEL),
          items: expandList(this.state.enemy.items, enemyDexes.length, null),
          movesets: expandList(this.state.enemy.movesets, enemyDexes.length, null),
        },
      };

      const mergedState: BattleLabState = {
        ...nextState,
        ...override,
        player: override?.player ? { ...nextState.player, ...override.player } : nextState.player,
        enemy: override?.enemy ? { ...nextState.enemy, ...override.enemy } : nextState.enemy,
      };

      return withMoveLabMove(mergedState);
    };

    const restartWithInputs = (override?: Partial<BattleLabState>) => {
      void this.restartBattle(getStateFromInputs(override));
    };

    const restartWithMove = (moveId: MoveId) => {
      const nextState = getStateFromInputs({
        selectedMove: moveId,
        playerPolicy: this.state.playerPolicy === "manual" ? "first" : this.state.playerPolicy,
      });
      void this.restartBattle(withMoveLabMove(nextState, moveId));
    };

    const createLeadCard = (
      label: string,
      inputValue: string,
      testIdPrefix: "player" | "enemy",
      fallback: number[],
      assignRefs: (
        input: HTMLInputElement,
        canvas: HTMLCanvasElement,
        liveLabel: HTMLDivElement,
        pendingLabel: HTMLDivElement,
      ) => void,
    ) => {
      const card = document.createElement("div");
      Object.assign(card.style, {
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "10px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.08)",
      } satisfies Partial<CSSStyleDeclaration>);

      const cardTitle = document.createElement("div");
      cardTitle.textContent = label;
      Object.assign(cardTitle.style, {
        fontWeight: "700",
        letterSpacing: "0.04em",
        fontSize: "11px",
        textTransform: "uppercase",
        color: "#b9d8ff",
      } satisfies Partial<CSSStyleDeclaration>);
      card.append(cardTitle);

      const previewRow = document.createElement("div");
      Object.assign(previewRow.style, {
        display: "flex",
        gap: "8px",
        alignItems: "center",
      } satisfies Partial<CSSStyleDeclaration>);

      const canvas = createPreviewCanvas();
      previewRow.append(canvas);

      const textCol = document.createElement("div");
      Object.assign(textCol.style, {
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        minWidth: "0",
      } satisfies Partial<CSSStyleDeclaration>);

      const liveLabel = document.createElement("div");
      Object.assign(liveLabel.style, {
        fontSize: "11px",
        color: "#f7f7f7",
        whiteSpace: "pre-line",
      } satisfies Partial<CSSStyleDeclaration>);
      textCol.append(liveLabel);

      const pendingLabel = document.createElement("div");
      Object.assign(pendingLabel.style, {
        fontSize: "10px",
        color: "#9fb8d7",
        whiteSpace: "pre-line",
      } satisfies Partial<CSSStyleDeclaration>);
      textCol.append(pendingLabel);

      previewRow.append(textCol);
      card.append(previewRow);

      const controlsRow = document.createElement("div");
      Object.assign(controlsRow.style, {
        display: "grid",
        gridTemplateColumns: "32px 1fr 32px",
        gap: "6px",
        alignItems: "center",
      } satisfies Partial<CSSStyleDeclaration>);

      const input = createInput(inputValue, `battle-lab-${testIdPrefix}-input`);
      input.addEventListener("input", () => this.refreshPreviewCards());

      controlsRow.append(
        createButton(
          "◀",
          () => {
            this.stepLeadInput(input, fallback, -1);
            restartWithInputs();
          },
          `battle-lab-${testIdPrefix}-prev`,
        ),
      );
      controlsRow.append(input);
      controlsRow.append(
        createButton(
          "▶",
          () => {
            this.stepLeadInput(input, fallback, 1);
            restartWithInputs();
          },
          `battle-lab-${testIdPrefix}-next`,
        ),
      );

      card.append(controlsRow);
      assignRefs(input, canvas, liveLabel, pendingLabel);
      return card;
    };

    if (this.state.moveLab) {
      root.append(this.createMoveLabPanel(restartWithMove));
    }

    sidesRow.append(
      createLeadCard(
        "Player Lead",
        this.state.player.dexes.join(","),
        "player",
        DEFAULT_PLAYER_TEAM,
        (input, canvas, liveLabel, pendingLabel) => {
          this.playerInput = input;
          this.playerPreviewCanvas = canvas;
          this.playerPreviewLiveLabel = liveLabel;
          this.playerPreviewPendingLabel = pendingLabel;
        },
      ),
    );
    sidesRow.append(
      createLeadCard(
        "Enemy Lead",
        this.state.enemy.dexes.join(","),
        "enemy",
        DEFAULT_ENEMY_TEAM,
        (input, canvas, liveLabel, pendingLabel) => {
          this.enemyInput = input;
          this.enemyPreviewCanvas = canvas;
          this.enemyPreviewLiveLabel = liveLabel;
          this.enemyPreviewPendingLabel = pendingLabel;
        },
      ),
    );

    root.append(sidesRow);

    const buttonRow = document.createElement("div");
    Object.assign(buttonRow.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "8px",
      alignItems: "center",
    } satisfies Partial<CSSStyleDeclaration>);

    buttonRow.append(
      createButton(
        "Swap",
        () => {
          if (!this.playerInput || !this.enemyInput) {
            return;
          }
          const nextPlayer = this.enemyInput.value;
          this.enemyInput.value = this.playerInput.value;
          this.playerInput.value = nextPlayer;
          this.refreshPreviewCards();
        },
        "battle-lab-swap",
      ),
    );
    buttonRow.append(
      createButton("Lineup Draft", () => restartWithInputs({ starterSelect: true }), "battle-lab-starter-select"),
    );
    buttonRow.append(createButton("Apply", () => restartWithInputs(), "battle-lab-go"));

    const hudButton = createButton(
      this.state.hideHud ? "Show HUD" : "Hide HUD",
      () => {
        this.state = { ...this.state, hideHud: !this.state.hideHud };
        hudButton.textContent = this.state.hideHud ? "Show HUD" : "Hide HUD";
        restartWithInputs({ hideHud: this.state.hideHud });
      },
      "battle-lab-hud-toggle",
    );
    buttonRow.append(hudButton);

    const modeButton = createButton(
      this.getModeLabel(),
      () => {
        const nextPolicy: BattleLabPlayerPolicy = this.state.playerPolicy === "manual" ? "smart" : "manual";
        this.state = { ...this.state, playerPolicy: nextPolicy };
        modeButton.textContent = nextPolicy === "manual" && !this.state.hideHud ? "Playable" : `Autoplay:${nextPolicy}`;
        restartWithInputs({ playerPolicy: nextPolicy });
      },
      "battle-lab-mode-toggle",
    );
    buttonRow.append(modeButton);
    buttonRow.append(createButton("Hide Overlay", () => this.setHelperUiVisible(false), "battle-lab-helper-hide"));

    const maybeSubmit = (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        restartWithInputs();
      }
    };
    this.playerInput?.addEventListener("keydown", maybeSubmit);
    this.enemyInput?.addEventListener("keydown", maybeSubmit);

    root.append(buttonRow);
    document.body.append(root);
    this.refreshPreviewCards();
    return root;
  }

  private createMoveLabPanel(restartWithMove: (moveId: MoveId) => void): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "move-lab-controls";
    Object.assign(root.style, {
      display: "grid",
      gap: "8px",
      padding: "10px",
      borderRadius: "12px",
      background: "linear-gradient(135deg, rgba(41, 99, 135, 0.34), rgba(168, 95, 38, 0.20))",
      border: "1px solid rgba(157, 218, 255, 0.22)",
    } satisfies Partial<CSSStyleDeclaration>);

    const title = document.createElement("div");
    title.textContent = "Move Lab";
    Object.assign(title.style, {
      color: "#d8f0ff",
      fontSize: "12px",
      fontWeight: "700",
      letterSpacing: "0.08em",
      textTransform: "uppercase",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(title);

    const inputRow = document.createElement("div");
    Object.assign(inputRow.style, {
      display: "grid",
      gridTemplateColumns: "32px 1fr 32px",
      gap: "6px",
      alignItems: "center",
    } satisfies Partial<CSSStyleDeclaration>);

    const optionsId = "move-lab-move-options";
    const options = document.createElement("datalist");
    options.id = optionsId;
    for (const moveId of getMoveLabMoveIds()) {
      const option = document.createElement("option");
      option.value = getMoveRouteName(moveId);
      option.label = `#${moveId} ${getMoveDisplayName(moveId)} · ${getMoveTypeLabel(moveId)} ${getMoveCategoryLabel(moveId)}`;
      options.append(option);
    }

    const createButton = (labelText: string, handler: () => void, testId: string) => {
      const button = document.createElement("button");
      button.textContent = labelText;
      button.dataset.testid = testId;
      Object.assign(button.style, {
        padding: "6px 8px",
        borderRadius: "8px",
        border: "1px solid rgba(255,255,255,0.18)",
        background: "rgba(255,255,255,0.08)",
        color: "#f7f7f7",
        cursor: "pointer",
      } satisfies Partial<CSSStyleDeclaration>);
      button.onclick = handler;
      return button;
    };

    const applyInputMove = () => {
      const moveId = this.resolveMoveInput();
      this.state = withMoveLabMove({ ...this.state, selectedMove: moveId }, moveId);
      this.renderMoveLabSummary(moveId);
      restartWithMove(moveId);
    };

    const input = document.createElement("input");
    input.type = "search";
    input.value = getMoveRouteName(this.state.selectedMove);
    input.setAttribute("list", optionsId);
    input.dataset.testid = "move-lab-move-input";
    this.moveInput = input;
    Object.assign(input.style, {
      width: "100%",
      padding: "6px 8px",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(5, 9, 14, 0.68)",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);
    input.addEventListener("input", () => this.renderMoveLabSummary(this.resolveMoveInput()));
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        applyInputMove();
      }
    });

    inputRow.append(
      createButton(
        "◀",
        () => {
          const moveId = this.findAdjacentMove(this.resolveMoveInput(), -1);
          input.value = getMoveRouteName(moveId);
          this.renderMoveLabSummary(moveId);
          restartWithMove(moveId);
        },
        "move-lab-prev",
      ),
      input,
      createButton(
        "▶",
        () => {
          const moveId = this.findAdjacentMove(this.resolveMoveInput(), 1);
          input.value = getMoveRouteName(moveId);
          this.renderMoveLabSummary(moveId);
          restartWithMove(moveId);
        },
        "move-lab-next",
      ),
    );
    root.append(inputRow, options);

    const summary = document.createElement("div");
    summary.dataset.testid = "move-lab-summary";
    this.moveSummaryRoot = summary;
    Object.assign(summary.style, {
      minHeight: "54px",
      padding: "8px",
      borderRadius: "10px",
      background: "rgba(5, 9, 14, 0.45)",
      color: "#dcecff",
      fontSize: "11px",
      lineHeight: "1.45",
      whiteSpace: "pre-line",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(summary);

    const buttonRow = document.createElement("div");
    Object.assign(buttonRow.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "6px",
    } satisfies Partial<CSSStyleDeclaration>);
    buttonRow.append(
      createButton("Replay Move", applyInputMove, "move-lab-replay"),
      createButton(
        "Random",
        () => {
          const moves = getMoveLabMoveIds();
          const moveId = moves[Math.floor(Math.random() * moves.length)] ?? this.state.selectedMove;
          input.value = getMoveRouteName(moveId);
          this.renderMoveLabSummary(moveId);
          restartWithMove(moveId);
        },
        "move-lab-random",
      ),
      createButton("Apply", applyInputMove, "move-lab-apply"),
    );
    root.append(buttonRow);

    const helper = document.createElement("div");
    helper.textContent = "Pinned to slot 1; Replay restarts the real battle and fires this move on turn one.";
    Object.assign(helper.style, {
      color: "#9fb8d7",
      fontSize: "10px",
      lineHeight: "1.35",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(helper);

    this.renderMoveLabSummary();
    return root;
  }

  private createHelperToggle(): HTMLButtonElement {
    const button = document.createElement("button");
    button.textContent = "Show Overlay";
    button.dataset.testid = "battle-lab-helper-show";
    Object.assign(button.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      zIndex: "9999",
      display: "none",
      padding: "6px 10px",
      borderRadius: "999px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(12, 15, 20, 0.92)",
      color: "#f7f7f7",
      fontFamily: "monospace",
      cursor: "pointer",
    } satisfies Partial<CSSStyleDeclaration>);
    button.onclick = () => this.setHelperUiVisible(true);
    document.body.append(button);
    return button;
  }

  private createStatus(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "battle-lab-status";
    Object.assign(root.style, {
      position: "fixed",
      left: "16px",
      bottom: "16px",
      zIndex: "9999",
      padding: "8px 10px",
      borderRadius: "10px",
      background: "rgba(10, 16, 24, 0.88)",
      border: "1px solid rgba(255,255,255,0.12)",
      fontFamily: "monospace",
      fontSize: "12px",
      color: "#cfe5ff",
      whiteSpace: "pre-line",
    } satisfies Partial<CSSStyleDeclaration>);
    root.textContent = "Preparing battle sandbox...";
    document.body.append(root);
    return root;
  }

  private stepLeadInput(input: HTMLInputElement, fallback: number[], direction: -1 | 1): void {
    const dexes = parseDexList(input.value, fallback);
    dexes[0] = this.findAdjacentDex(dexes[0] ?? fallback[0], direction);
    input.value = dexes.join(",");
    this.refreshPreviewCards();
  }

  private findAdjacentDex(currentDex: number, direction: -1 | 1): number {
    if (BATTLE_LAB_SPECIES_IDS.length === 0) {
      return currentDex;
    }

    const exactIndex = BATTLE_LAB_SPECIES_IDS.indexOf(currentDex);
    if (exactIndex !== -1) {
      const nextIndex = (exactIndex + direction + BATTLE_LAB_SPECIES_IDS.length) % BATTLE_LAB_SPECIES_IDS.length;
      return BATTLE_LAB_SPECIES_IDS[nextIndex];
    }

    const fallbackIndex = BATTLE_LAB_SPECIES_IDS.findIndex(speciesId => speciesId > currentDex);
    if (direction > 0) {
      return fallbackIndex === -1 ? BATTLE_LAB_SPECIES_IDS[0] : BATTLE_LAB_SPECIES_IDS[fallbackIndex];
    }

    if (fallbackIndex <= 0) {
      return BATTLE_LAB_SPECIES_IDS.at(-1) ?? currentDex;
    }

    return BATTLE_LAB_SPECIES_IDS[fallbackIndex - 1];
  }

  private resolveMoveInput(): MoveId {
    return resolveMoveIdOrFallback(this.moveInput?.value ?? null, this.state.selectedMove);
  }

  private findAdjacentMove(currentMove: MoveId, direction: -1 | 1): MoveId {
    const moveIds = getMoveLabMoveIds();
    if (moveIds.length === 0) {
      return currentMove;
    }

    const exactIndex = moveIds.indexOf(currentMove);
    if (exactIndex !== -1) {
      const nextIndex = (exactIndex + direction + moveIds.length) % moveIds.length;
      return moveIds[nextIndex];
    }

    const fallbackIndex = moveIds.findIndex(moveId => moveId > currentMove);
    if (direction > 0) {
      return fallbackIndex === -1 ? moveIds[0] : moveIds[fallbackIndex];
    }

    if (fallbackIndex <= 0) {
      return moveIds.at(-1) ?? currentMove;
    }

    return moveIds[fallbackIndex - 1];
  }

  private renderMoveLabSummary(moveId = this.state.selectedMove): void {
    if (!this.moveSummaryRoot) {
      return;
    }

    const move = allMoves[moveId];
    if (!move) {
      this.moveSummaryRoot.textContent = `Unknown move: ${this.moveInput?.value ?? moveId}`;
      return;
    }

    const power = move.power >= 0 ? String(move.power) : "--";
    const accuracy = move.accuracy >= 0 ? String(move.accuracy) : "--";
    const effect = move.effect ? `\n${move.effect}` : "";
    this.moveSummaryRoot.textContent =
      `#${moveId} ${getMoveDisplayName(moveId)} (${getMoveRouteName(moveId)})\n`
      + `${getMoveTypeLabel(moveId)} / ${getMoveCategoryLabel(moveId)} · power ${power} · acc ${accuracy} · pp ${move.pp}${effect}`;
  }

  private refreshPreviewCards(): void {
    this.renderMoveLabSummary(this.resolveMoveInput());
    this.renderLivePreview(
      this.playerPreviewCanvas,
      this.playerPreviewLiveLabel,
      this.scene.getPlayerPokemon(true),
      "Player",
    );
    this.renderLivePreview(
      this.enemyPreviewCanvas,
      this.enemyPreviewLiveLabel,
      this.scene.getEnemyPokemon(true),
      "Enemy",
    );

    if (this.playerPreviewPendingLabel) {
      this.playerPreviewPendingLabel.textContent = this.describePendingPreview(
        this.playerInput?.value ?? "",
        DEFAULT_PLAYER_TEAM,
      );
    }
    if (this.enemyPreviewPendingLabel) {
      this.enemyPreviewPendingLabel.textContent = this.describePendingPreview(
        this.enemyInput?.value ?? "",
        DEFAULT_ENEMY_TEAM,
      );
    }
  }

  private describePendingPreview(rawValue: string, fallback: number[]): string {
    const dexes = parseDexList(rawValue, fallback);
    const leadDex = dexes[0];
    const leadSpecies = getPokemonSpecies(leadDex);
    const benchCount = Math.max(dexes.length - 1, 0);
    const routeLabel = dexes.join(",");
    return `Next load: #${leadDex.toString().padStart(4, "0")} ${leadSpecies.name}${benchCount > 0 ? ` (+${benchCount} bench)` : ""}\nRoute: ${routeLabel}`;
  }

  private renderLivePreview(
    canvas: HTMLCanvasElement | null,
    liveLabel: HTMLDivElement | null,
    pokemon: PlayerPokemon | EnemyPokemon | undefined,
    fallbackLabel: string,
  ): void {
    if (!canvas || !liveLabel) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "rgba(6, 10, 16, 0.96)";
    context.fillRect(0, 0, canvas.width, canvas.height);

    if (!pokemon) {
      liveLabel.textContent = `${fallbackLabel}: none`;
      return;
    }

    liveLabel.textContent = `Live: ${pokemon.name}\nLv${pokemon.level}  HP ${pokemon.hp}/${pokemon.getMaxHp()}`;

    const sprite = pokemon.getSprite();
    const frame = sprite?.frame as Phaser.Textures.Frame | undefined;
    const sourceImage = (frame?.source as { image?: CanvasImageSource } | undefined)?.image;
    if (!frame || !sourceImage) {
      return;
    }

    const sourceWidth = frame.cutWidth ?? frame.width;
    const sourceHeight = frame.cutHeight ?? frame.height;
    const drawScale = Math.min((canvas.width - 8) / sourceWidth, (canvas.height - 8) / sourceHeight);
    const drawWidth = Math.max(1, Math.floor(sourceWidth * drawScale));
    const drawHeight = Math.max(1, Math.floor(sourceHeight * drawScale));
    const drawX = Math.floor((canvas.width - drawWidth) / 2);
    const drawY = Math.floor((canvas.height - drawHeight) / 2);

    context.imageSmoothingEnabled = false;
    context.drawImage(
      sourceImage,
      frame.cutX ?? 0,
      frame.cutY ?? 0,
      sourceWidth,
      sourceHeight,
      drawX,
      drawY,
      drawWidth,
      drawHeight,
    );
  }

  private setHelperUiVisible(visible: boolean): void {
    this.helperUiVisible = visible;
    this.updateHelperUiVisibility();
  }

  private updateHelperUiVisibility(): void {
    if (!this.state.debugUi) {
      return;
    }

    if (this.controlsRoot) {
      this.controlsRoot.style.display = this.helperUiVisible ? "flex" : "none";
    }
    if (this.statusRoot) {
      this.statusRoot.style.display = this.helperUiVisible ? "block" : "none";
    }
    if (this.helperToggleRoot) {
      this.helperToggleRoot.style.display = this.helperUiVisible ? "none" : "block";
    }
  }

  private renderStatus(message?: string): void {
    this.refreshPreviewCards();

    if (!this.statusRoot) {
      return;
    }

    if (message) {
      this.statusRoot.textContent = message;
      return;
    }

    const currentPhase = this.scene.phaseManager.getCurrentPhase?.();
    const player = this.scene.getPlayerPokemon(true);
    const enemy = this.scene.getEnemyPokemon(true);
    const lines = [
      this.state.moveLab ? "Move Lab Sandbox" : "Playable Battle Sandbox",
      `Phase: ${currentPhase?.phaseName ?? "idle"}`,
      `Turn: ${this.scene.currentBattle?.turn ?? 0}`,
      `Team: ${this.describePokemon(player)}`,
      `Opponent: ${this.describePokemon(enemy)}`,
      `Lineup Draft: ${this.state.starterSelect ? "open" : "set"}`,
      `Control: ${this.getModeLabel()}`,
      `Battle HUD: ${this.state.hideHud ? "hidden" : "visible"}`,
    ];

    if (this.state.moveLab) {
      lines.push(`Move: ${getMoveDisplayName(this.state.selectedMove)} (${getMoveRouteName(this.state.selectedMove)})`);
    }

    if (this.frozenResult) {
      lines.push(`Result: ${this.frozenResult}`);
    }

    this.statusRoot.textContent = lines.join("\n");
  }

  private async restartBattle(nextState: BattleLabState): Promise<void> {
    if (this.restartingBattle) {
      this.pendingRestartState = withMoveLabMove(nextState);
      this.state = this.pendingRestartState;
      writeBattleLabState(this.state);
      this.refreshPreviewCards();
      this.renderStatus("Queued battle setup...");
      return;
    }

    this.restartingBattle = true;
    try {
      let restartState: BattleLabState | null = nextState;
      while (restartState) {
        this.pendingRestartState = null;
        await this.performRestart(restartState);
        if (restartState.starterSelect) {
          return;
        }
        restartState = this.pendingRestartState;
      }
    } catch (error) {
      console.error("Battle lab restart failed", error);
      const message = error instanceof Error ? error.message : String(error);
      this.renderStatus(`Battle lab restart failed: ${message}`);
      showBattleLabError(message);
    } finally {
      this.restartingBattle = false;
    }
  }

  private async performRestart(nextState: BattleLabState): Promise<void> {
    this.state = withMoveLabMove(nextState);
    writeBattleLabState(this.state);
    this.frozenResult = null;
    this.lastMoveCursorByPokemonId.clear();

    if (!this.state.starterSelect) {
      this.selectedStarters = null;
    }

    this.renderStatus(this.state.starterSelect ? "Opening roster cache..." : "Swapping live battle setup...");
    this.scene.phaseManager.clearAllPhases();
    this.setSetupPhase();
    this.resetTransientBattleUi();
    this.scene.reset(false, false, false);
    this.unlockGeneratedStarters();
    this.hideHud();

    if (this.state.starterSelect) {
      this.openStarterSelect();
      return;
    }

    await this.beginBattle();
  }

  private setSetupPhase(): void {
    (
      this.scene.phaseManager as unknown as {
        currentPhase: { is: (phaseName: string) => boolean; phaseName: string };
      }
    ).currentPhase = {
      is: () => false,
      phaseName: "BattleLabSetupPhase",
    };
  }

  private resetTransientBattleUi(): void {
    this.scene.time.removeAllEvents();
    this.scene.tweens.killAll();
    this.scene.pbTray.reset();
    this.scene.pbTrayEnemy.reset();
  }

  private describePokemon(pokemon: PlayerPokemon | EnemyPokemon | undefined): string {
    if (!pokemon) {
      return "none";
    }

    const status = pokemon.status?.effect ? ` ${pokemon.status?.effect}` : "";
    return `${pokemon.name} Lv${pokemon.level} HP ${pokemon.hp}/${pokemon.getMaxHp()}${status}`;
  }

  private installPhaseHooks(): void {
    const phaseManager = this.scene.phaseManager as typeof this.scene.phaseManager & {
      create: (...args: unknown[]) => unknown;
      queueMessage: (...args: unknown[]) => void;
    };
    const originalCreate = phaseManager.create.bind(phaseManager);
    const originalQueueMessage = phaseManager.queueMessage.bind(phaseManager);

    phaseManager.create = ((phaseName: string, ...args: unknown[]) => {
      const phase = originalCreate(phaseName, ...args);
      return this.decoratePhase(phaseName, phase);
    }) as typeof phaseManager.create;

    if (this.isAutoplayMode()) {
      phaseManager.queueMessage = ((
        message: string,
        callbackDelay?: number | null,
        prompt?: boolean | null,
        promptDelay?: number | null,
        defer?: boolean | null,
      ) => {
        const phase = phaseManager.create("MessagePhase", message, callbackDelay, prompt, promptDelay) as never;
        if (defer) {
          this.scene.phaseManager.pushPhase(phase);
        } else {
          this.scene.phaseManager.unshiftPhase(phase);
        }
      }) as typeof phaseManager.queueMessage;
    }

    this.restorePhaseFactory = () => {
      phaseManager.create = originalCreate as typeof phaseManager.create;
      phaseManager.queueMessage = originalQueueMessage as typeof phaseManager.queueMessage;
    };
  }

  private decoratePhase(phaseName: string, phase: unknown): unknown {
    const autoplay = this.isAutoplayMode();
    switch (phaseName) {
      case "CommandPhase":
        return autoplay ? this.decorateCommandPhase(phase) : phase;
      case "SwitchPhase":
        return autoplay ? this.decorateSwitchPhase(phase) : phase;
      case "MessagePhase":
        return autoplay ? this.decorateMessagePhase(phase) : phase;
      case "SelectTargetPhase":
        return autoplay ? this.decorateSelectTargetPhase(phase) : phase;
      case "BattleEndPhase":
        return this.decorateBattleEndPhase(phase);
      case "GameOverPhase":
        return this.decorateGameOverPhase(phase);
      default:
        return phase;
    }
  }

  private decorateCommandPhase(phase: unknown): unknown {
    const commandPhase = phase as {
      start: () => void;
      getPokemon: () => PlayerPokemon;
      handleCommand: (
        command: Command,
        cursor: number,
        useMode?: MoveUseMode,
        move?: { move: MoveId; targets: number[]; useMode: MoveUseMode },
      ) => boolean;
    };

    commandPhase.start = () => {
      this.hideHud();
      this.renderStatus();

      const pokemon = commandPhase.getPokemon();
      const moveChoice = this.chooseMove(pokemon);

      if (moveChoice) {
        commandPhase.handleCommand(Command.FIGHT, moveChoice.cursor, MoveUseMode.NORMAL, {
          move: moveChoice.moveId,
          targets: moveChoice.targets,
          useMode: MoveUseMode.NORMAL,
        });
        return;
      }

      commandPhase.handleCommand(Command.FIGHT, 0);
    };

    return commandPhase;
  }

  private decorateSwitchPhase(phase: unknown): unknown {
    const switchPhase = phase as {
      start: () => void;
      end: () => void;
      fieldIndex: number;
      switchType: unknown;
      doReturn: boolean;
    };

    switchPhase.start = () => {
      this.hideHud();
      this.renderStatus();

      const slotIndex = this.getNextPlayerSwitchSlot();
      if (slotIndex === -1) {
        switchPhase.end();
        return;
      }

      this.scene.phaseManager.unshiftNew(
        "SwitchSummonPhase",
        switchPhase.switchType as never,
        switchPhase.fieldIndex as never,
        slotIndex as never,
        switchPhase.doReturn as never,
      );
      switchPhase.end();
    };

    return switchPhase;
  }

  private decorateMessagePhase(phase: unknown): unknown {
    const messagePhase = phase as {
      start: () => void;
      end: () => void;
      text?: string;
      callbackDelay?: number | null;
      prompt?: boolean | null;
      promptDelay?: number | null;
      speaker?: string;
    };

    messagePhase.start = () => {
      const text = messagePhase.text ?? "";
      const pageIndex = text.indexOf("$");
      if (pageIndex !== -1) {
        const nextPage = text.slice(pageIndex + 1).trim();
        if (nextPage) {
          this.scene.phaseManager.unshiftNew(
            "MessagePhase",
            nextPage,
            messagePhase.callbackDelay ?? undefined,
            false,
            0,
            messagePhase.speaker,
          );
        }
        messagePhase.text = text.slice(0, pageIndex).trim();
      }

      const delay = Math.min(Math.max(messagePhase.callbackDelay ?? 0, 350), 1000);
      this.scene.time.delayedCall(delay, () => messagePhase.end());
    };

    return messagePhase;
  }

  private decorateSelectTargetPhase(phase: unknown): unknown {
    const selectTargetPhase = phase as {
      start: () => void;
      end: () => void;
      fieldIndex: number;
    };

    selectTargetPhase.start = () => {
      const fieldIndex = selectTargetPhase.fieldIndex;
      const turnCommand = this.scene.currentBattle.turnCommands[fieldIndex];
      const user = this.scene.getField()[fieldIndex];
      const moveId = turnCommand?.move?.move;

      if (!user || !moveId) {
        selectTargetPhase.end();
        return;
      }

      turnCommand.targets = this.resolveTargets(user, moveId);
      selectTargetPhase.end();
    };

    return selectTargetPhase;
  }

  private decorateBattleEndPhase(phase: unknown): unknown {
    const battleEndPhase = phase as {
      start: () => void;
      end: () => void;
      isVictory: boolean;
    };
    const originalStart = battleEndPhase.start.bind(battleEndPhase);

    battleEndPhase.end = () => {
      this.scene.phaseManager.clearPhaseQueue();
      this.hideHud();
      this.frozenResult = battleEndPhase.isVictory ? "player-won" : "battle-ended";
      this.renderStatus();
    };

    battleEndPhase.start = () => {
      originalStart();
      this.renderStatus();
    };

    return battleEndPhase;
  }

  private decorateGameOverPhase(phase: unknown): unknown {
    const gameOverPhase = phase as {
      start: () => void;
    };

    gameOverPhase.start = () => {
      this.scene.phaseManager.clearPhaseQueue();
      this.hideHud();
      this.frozenResult = "enemy-won";
      this.renderStatus();
    };

    return gameOverPhase;
  }

  private chooseMove(pokemon: PlayerPokemon): MoveChoice | null {
    const candidates = pokemon
      .getMoveset()
      .map((move, cursor) => {
        const [usable] = move.isUsable(pokemon, false, true);
        if (!usable) {
          return null;
        }

        const moveId = move.moveId;
        const targets = this.resolveTargets(pokemon, moveId);
        const effectivePower = allMoves[moveId].calculateEffectivePower(pokemon);
        return {
          cursor,
          moveId,
          targets,
          score: effectivePower > 0 ? 1000 + effectivePower : 10 - cursor,
        } satisfies MoveChoice;
      })
      .filter((choice): choice is MoveChoice => !!choice);

    if (candidates.length === 0) {
      return null;
    }

    switch (this.state.playerPolicy) {
      case "first":
        return candidates[0];
      case "random":
        return candidates[Math.floor(Math.random() * candidates.length)];
      case "cycle": {
        const lastCursor = this.lastMoveCursorByPokemonId.get(pokemon.id) ?? -1;
        const cycled = candidates.find(choice => choice.cursor > lastCursor) ?? candidates[0];
        this.lastMoveCursorByPokemonId.set(pokemon.id, cycled.cursor);
        return cycled;
      }
      default: {
        const best = [...candidates].sort((left, right) => right.score - left.score)[0];
        this.lastMoveCursorByPokemonId.set(pokemon.id, best.cursor);
        return best;
      }
    }
  }

  private resolveTargets(user: Pokemon, moveId: MoveId): number[] {
    const moveTargets = getMoveTargets(user, moveId);
    if (moveTargets.targets.length > 0) {
      return moveTargets.multiple ? moveTargets.targets : moveTargets.targets.slice(0, 1);
    }

    const move = allMoves[moveId];
    const enemy = user.isPlayer() ? this.scene.getEnemyPokemon(true) : this.scene.getPlayerPokemon(true);
    if (enemy && move.calculateEffectivePower(user) > 0) {
      return [enemy.getBattlerIndex()];
    }

    return [user.getBattlerIndex()];
  }

  private getNextPlayerSwitchSlot(): number {
    const battlerCount = this.scene.currentBattle.getBattlerCount();
    return this.scene
      .getPlayerParty()
      .findIndex((pokemon, index) => index >= battlerCount && pokemon.isAllowedInBattle() && !pokemon.isOnField());
  }

  private async bootBattle(): Promise<void> {
    this.scene.phaseManager.clearAllPhases();
    this.setSetupPhase();
    this.scene.battleStyle = BattleStyle.SET;
    this.scene.newArena(this.state.biome);
    this.scene.arena.init();
    this.scene.field.setVisible(true);
    this.scene.trainer.setVisible(true);

    const enemyTrainer = new Trainer(TrainerType.ACE_TRAINER, TrainerVariant.DEFAULT);
    const battle = new Battle(this.scene.gameMode, {
      waveIndex: 1,
      battleType: BattleType.TRAINER,
      trainer: enemyTrainer,
      double: false,
    });
    battle.incrementTurn();
    battle.started = true;
    this.scene.currentBattle = battle;

    const playerParty = this.createPlayerParty(this.state.player);
    const enemyParty = this.createEnemyParty(this.state.enemy);

    this.scene.getPlayerParty().push(...playerParty);
    this.scene.currentBattle.enemyParty.push(...enemyParty);

    await Promise.all([
      ...playerParty.map(pokemon => pokemon.loadAssets()),
      ...enemyParty.map(pokemon => pokemon.loadAssets()),
      enemyTrainer.loadAssets().then(() => enemyTrainer.initSprite()),
    ]);

    this.scene.add.existing(enemyTrainer);
    this.scene.field.add(enemyTrainer);
    enemyTrainer.setVisible(false);
    enemyTrainer.setAlpha(0);

    await this.applyHeldItems(playerParty, this.state.player.items, true);
    await this.applyHeldItems(enemyParty, this.state.enemy.items, false);

    await this.placeEnemy(enemyParty[0]);
    this.scene.currentBattle.seenEnemyPartyMemberIds.add(enemyParty[0].id);
    this.scene.currentBattle.trainer?.genAI(this.scene.getEnemyParty());
    await this.scene.updateFieldScale();
    this.hideHud();

    this.scene.phaseManager.pushNew("SummonPhase", 0);
    this.scene.phaseManager.pushNew("PostSummonPhase", enemyParty[0].getBattlerIndex());
    this.scene.phaseManager.pushNew("PostSummonPhase", 0);
    this.scene.phaseManager.shiftPhase();
  }

  private createPlayerParty(config: BattleLabSideState): PlayerPokemon[] {
    if (this.selectedStarters) {
      return this.createPlayerPartyFromStarters(this.selectedStarters, config);
    }

    return config.dexes.map((dex, index) => {
      const species = getPokemonSpecies(dex);
      if (!species) {
        throw new Error(`Player dex ${dex} does not exist.`);
      }

      const pokemon = this.scene.addPlayerPokemon(species, config.levels[index] ?? DEFAULT_LEVEL);
      pokemon.generateAndPopulateMoveset();

      const moveset = config.movesets[index];
      if (moveset != null && moveset.length > 0) {
        pokemon.tryPopulateMoveset(
          moveset as [MoveId] | [MoveId, MoveId] | [MoveId, MoveId, MoveId] | [MoveId, MoveId, MoveId, MoveId],
          true,
        );
      }

      return pokemon;
    });
  }

  private createPlayerPartyFromStarters(starters: Starter[], config: BattleLabSideState): PlayerPokemon[] {
    return starters.map((starter, index) => {
      const species = getPokemonSpecies(starter.speciesId);
      if (!species) {
        throw new Error(`Starter dex ${starter.speciesId} does not exist.`);
      }

      const gender = species.malePercent !== null ? (starter.female ? Gender.FEMALE : Gender.MALE) : Gender.GENDERLESS;
      const pokemon = this.scene.addPlayerPokemon(
        species,
        config.levels[index] ?? DEFAULT_LEVEL,
        starter.abilityIndex,
        starter.formIndex,
        gender,
        starter.shiny,
        starter.variant,
        starter.ivs,
        starter.nature,
      );

      if (starter.moveset) {
        pokemon.tryPopulateMoveset(starter.moveset, true);
      } else {
        pokemon.generateAndPopulateMoveset();
      }

      if (starter.passive) {
        pokemon.passive = true;
      }

      if (starter.pokerus) {
        pokemon.pokerus = true;
      }

      if (starter.nickname) {
        pokemon.nickname = starter.nickname;
      }

      pokemon.teraType = starter.teraType ?? pokemon.species.type1;
      return pokemon;
    });
  }

  private createEnemyParty(config: BattleLabSideState): EnemyPokemon[] {
    return config.dexes.map((dex, index) => {
      const species = getPokemonSpecies(dex);
      if (!species) {
        throw new Error(`Enemy dex ${dex} does not exist.`);
      }

      const pokemon = this.scene.addEnemyPokemon(species, config.levels[index] ?? DEFAULT_LEVEL, TrainerSlot.TRAINER);
      pokemon.generateAndPopulateMoveset();

      const moveset = config.movesets[index];
      if (moveset != null && moveset.length > 0) {
        pokemon.tryPopulateMoveset(
          moveset as [MoveId] | [MoveId, MoveId] | [MoveId, MoveId, MoveId] | [MoveId, MoveId, MoveId, MoveId],
          true,
        );
      }

      return pokemon;
    });
  }

  private async applyHeldItems(
    party: (PlayerPokemon | EnemyPokemon)[],
    items: (string | null)[],
    playerSide: boolean,
  ): Promise<void> {
    for (let index = 0; index < party.length; index++) {
      const itemName = items[index];
      if (!itemName) {
        continue;
      }

      const modifierTypeFunc = (modifierTypes as Record<string, unknown>)[normalizeLookupKey(itemName)];
      if (typeof modifierTypeFunc !== "function") {
        throw new Error(`Unknown held item "${itemName}"`);
      }

      const modifier = getModifierType(modifierTypeFunc as ModifierTypeFunc).newModifier(party[index] as Pokemon) as
        | PersistentModifier
        | undefined;
      if (!modifier) {
        throw new Error(`Unable to create held item "${itemName}"`);
      }

      if (playerSide) {
        this.scene.addModifier(modifier, true, false, false, true);
      } else {
        await this.scene.addEnemyModifier(modifier, true, true);
      }
    }

    this.scene.updateModifiers(playerSide, true);
  }

  private async placeEnemy(enemy: EnemyPokemon): Promise<void> {
    await enemy.setFieldPosition(FieldPosition.CENTER, 0);
    this.scene.add.existing(enemy);
    this.scene.field.add(enemy);
    this.scene.field.moveBelow(
      enemy as Phaser.GameObjects.GameObject,
      this.scene.trainer as Phaser.GameObjects.GameObject,
    );
    enemy.setVisible(true);
    enemy.getSprite().setVisible(true);
    enemy.setScale(enemy.getSpriteScale());
    enemy.playAnim();
    enemy.fieldSetup(true);
    await enemy.updateInfo(true);
    enemy.showInfo();
  }

  private hideHud(): void {
    if (this.state.hideHud) {
      this.scene.fieldUI.setVisible(false);
      this.scene.uiContainer.setVisible(false);
      return;
    }

    this.scene.fieldUI.setVisible(true);
    this.scene.uiContainer.setVisible(true);
  }

  destroy(): void {
    if (this.restorePhaseFactory) {
      this.restorePhaseFactory();
      this.restorePhaseFactory = null;
    }
    if (this.statusTimerId != null) {
      window.clearInterval(this.statusTimerId);
      this.statusTimerId = null;
    }
    this.controlsRoot?.remove();
    this.statusRoot?.remove();
    this.helperToggleRoot?.remove();
  }
}

export async function maybeStartBattleLab(scene: BattleScene): Promise<boolean> {
  try {
    const state = parseBattleLabState();
    if (!state) {
      return false;
    }

    writeBattleLabState(state);
    const lab = new BattleLab(scene, state);
    await lab.start();
    return true;
  } catch (error) {
    console.error("Battle lab startup failed", error);
    showBattleLabError(error instanceof Error ? error.message : String(error));
    return true;
  }
}
