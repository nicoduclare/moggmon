import type { BattleScene } from "#app/battle-scene";
import { Phase } from "#app/phase";
import { getEvolutions, pokemonEvolutions, type SpeciesFormEvolution } from "#balance/pokemon-evolutions";
import { isDev } from "#constants/app-constants";
import { Button } from "#enums/buttons";
import type { PlayerPokemon } from "#field/pokemon";
import { getPokemonSpecies } from "#utils/pokemon-utils";

const ENABLE_PARAM = "evolutionLab";
const DEX_PARAM = "dex";
const PREVIEW_LEVEL = 42;

type EvolutionLabState = {
  dex: number;
};

type FamilyStageAsset = {
  dex: number;
  name: string;
  iconKey: string;
  iconFrame: string;
  frontKey: string;
};

type EvolutionPair = {
  fromDex: number;
  toDex: number;
};

type GameDataWriteOverrides = {
  setPokemonCaught: unknown;
  setPokemonSeen: unknown;
  updateSpeciesDexIvs: unknown;
};

function parseEvolutionLabState(): EvolutionLabState | null {
  if (!isDev) {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get(ENABLE_PARAM) !== "1") {
    return null;
  }

  const rawDex = Number.parseInt(params.get(DEX_PARAM) || "1", 10);
  return {
    dex: Number.isFinite(rawDex) && rawDex > 0 ? rawDex : 1,
  };
}

function writeEvolutionLabState(state: EvolutionLabState): void {
  const url = new URL(window.location.href);
  url.searchParams.set(ENABLE_PARAM, "1");
  url.searchParams.set(DEX_PARAM, String(state.dex));
  window.history.replaceState({}, "", url);
}

function textStyle(fontSize: string, color = "#f7f7f7"): Phaser.Types.GameObjects.Text.TextStyle {
  return {
    fontFamily: "emerald",
    fontSize,
    color,
  };
}

function ensureLoopingAnimation(scene: BattleScene, key: string): void {
  if (scene.anims.exists(key)) {
    return;
  }

  const originalWarn = console.warn;
  console.warn = () => {};
  const frameNames = scene.anims.generateFrameNames(key, {
    zeroPad: 4,
    suffix: ".png",
    start: 1,
    end: 400,
  });
  console.warn = originalWarn;

  if (frameNames.length === 0) {
    return;
  }

  scene.anims.create({
    key,
    frames: frameNames,
    frameRate: 10,
    repeat: -1,
  });
}

function getFamilyDexes(dex: number): number[] {
  const species = getPokemonSpecies(dex);
  const rootDex = species.getRootSpeciesId();
  return Array.from(new Set([rootDex, ...getEvolutions(rootDex).values()]));
}

function resolvePreviewPair(familyDexes: number[], dex: number): EvolutionPair | null {
  if (familyDexes.length === 0) {
    return null;
  }

  const currentIndex = Math.max(0, familyDexes.indexOf(dex));
  if (currentIndex < familyDexes.length - 1) {
    return {
      fromDex: familyDexes[currentIndex],
      toDex: familyDexes[currentIndex + 1],
    };
  }

  if (currentIndex > 0) {
    return {
      fromDex: familyDexes[currentIndex - 1],
      toDex: familyDexes[currentIndex],
    };
  }

  return null;
}

function resolveEvolution(fromDex: number, toDex: number): SpeciesFormEvolution | null {
  const evolutions = pokemonEvolutions[fromDex] ?? [];
  return evolutions.find(evolution => evolution.speciesId === toDex) ?? null;
}

async function loadFamilyAssets(scene: BattleScene, dexes: number[]): Promise<FamilyStageAsset[]> {
  const assets: FamilyStageAsset[] = [];

  for (const dex of dexes) {
    const species = getPokemonSpecies(dex);
    await species.loadAssets(false, 0, false, 0, true, false);

    const frontKey = species.getSpriteKey(false, 0, false, 0, false);
    ensureLoopingAnimation(scene, frontKey);

    assets.push({
      dex,
      name: species.name,
      iconKey: species.getIconAtlasKey(0, false, 0),
      iconFrame: species.getIconId(false, 0, false, 0),
      frontKey,
    });
  }

  return assets;
}

class EvolutionLabReturnPhase extends Phase {
  public readonly phaseName = "UnavailablePhase";

  constructor(private readonly onReturn: () => void) {
    super();
  }

  start(): void {
    super.start();
    this.onReturn();
  }
}

class EvolutionLab {
  private readonly scene: BattleScene;
  private state: EvolutionLabState;
  private readonly root: Phaser.GameObjects.Container;
  private readonly content: Phaser.GameObjects.Container;
  private readonly bg: Phaser.GameObjects.Rectangle;
  private readonly titleText: Phaser.GameObjects.Text;
  private readonly subtitleText: Phaser.GameObjects.Text;
  private readonly statusText: Phaser.GameObjects.Text;
  private readonly controlsRoot: HTMLDivElement;
  private currentFamilyDexes: number[] = [];
  private currentPreviewPair: EvolutionPair | null = null;
  private previewFromSprite: Phaser.GameObjects.Sprite | null = null;
  private previewToSprite: Phaser.GameObjects.Sprite | null = null;
  private previewFlash: Phaser.GameObjects.Rectangle | null = null;
  private previewFromLabel: Phaser.GameObjects.Text | null = null;
  private previewToLabel: Phaser.GameObjects.Text | null = null;
  private previewDirectionLabel: Phaser.GameObjects.Text | null = null;
  private renderToken = 0;
  private playingEvolutionScene = false;
  private activeEvolutionPokemon: PlayerPokemon | null = null;
  private gameDataOverrides: GameDataWriteOverrides | null = null;
  private autoAdvanceTimerId: number | null = null;

  constructor(scene: BattleScene, state: EvolutionLabState) {
    this.scene = scene;
    this.state = state;

    const width = Number(scene.scale.width) || 1920;
    const height = Number(scene.scale.height) || 1080;

    this.root = scene.add.container(0, 0).setDepth(1000);
    this.bg = scene.add.rectangle(0, 0, width, height, 0x14161b, 0.98).setOrigin(0);
    this.content = scene.add.container(0, 0);
    this.titleText = scene.add.text(48, 28, "Mogger Mon Maxx Lab", textStyle("46px"));
    this.subtitleText = scene.add.text(48, 82, "", textStyle("24px", "#aab8c7"));
    this.statusText = scene.add.text(48, height - 42, "", textStyle("20px", "#9ad1ff"));

    this.root.add([this.bg, this.content, this.titleText, this.subtitleText, this.statusText]);
    this.controlsRoot = this.createControls();
    scene.events.once(Phaser.Scenes.Events.DESTROY, () => this.destroy());
  }

  async start(): Promise<void> {
    await this.render();
  }

  private createControls(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "evolution-lab-controls";
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
    input.min = "1";
    input.value = String(this.state.dex);
    input.dataset.testid = "evolution-lab-dex-input";
    Object.assign(input.style, {
      width: "72px",
      padding: "6px 8px",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);
    root.append(input);

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

    const setDex = (dex: number) => {
      this.state = { dex: Math.max(1, Math.floor(dex || 1)) };
      input.value = String(this.state.dex);
      writeEvolutionLabState(this.state);
      void this.render();
    };

    const shiftStage = (delta: number) => {
      if (this.currentFamilyDexes.length === 0) {
        return;
      }
      const currentIndex = Math.max(0, this.currentFamilyDexes.indexOf(this.state.dex));
      const nextIndex = Phaser.Math.Clamp(currentIndex + delta, 0, this.currentFamilyDexes.length - 1);
      setDex(this.currentFamilyDexes[nextIndex]);
    };

    attachButton("Prev", () => setDex(this.state.dex - 1), "evolution-lab-prev");
    attachButton("Next", () => setDex(this.state.dex + 1), "evolution-lab-next");
    attachButton("Prev Stage", () => shiftStage(-1), "evolution-lab-prev-stage");
    attachButton("Next Stage", () => shiftStage(1), "evolution-lab-next-stage");
    attachButton("Play Maxx Scene", () => void this.playEvolution(), "evolution-lab-play");
    attachButton("Go", () => setDex(Number.parseInt(input.value || "1", 10)), "evolution-lab-go");

    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        setDex(Number.parseInt(input.value || "1", 10));
      }
    });

    document.body.append(root);
    return root;
  }

  private addPanel(x: number, y: number, width: number, height: number, title: string): Phaser.GameObjects.Container {
    const panel = this.scene.add.container(x, y);
    panel.add([
      this.scene.add.rectangle(0, 0, width, height, 0x10151d, 0.95).setOrigin(0),
      this.scene.add.rectangle(0, 0, width, height).setOrigin(0).setStrokeStyle(2, 0x344051, 1),
      this.scene.add.text(20, 16, title, textStyle("28px")),
    ]);
    this.content.add(panel);
    return panel;
  }

  private addPreviewSprite(
    panel: Phaser.GameObjects.Container,
    x: number,
    y: number,
    key: string,
    scale: number,
  ): Phaser.GameObjects.Sprite {
    const sprite = this.scene.add.sprite(x, y, key).setOrigin(0.5, 1).setScale(scale);
    const texture = this.scene.textures.get(key);
    if (texture.has("0001.png")) {
      sprite.setFrame("0001.png");
    } else if (this.scene.anims.exists(key)) {
      sprite.play(key);
    }
    panel.add(sprite);
    return sprite;
  }

  private addFamilyStageCard(
    panel: Phaser.GameObjects.Container,
    asset: FamilyStageAsset,
    x: number,
    width: number,
    selected: boolean,
    stageLabel: string,
  ): void {
    const cardY = 70;
    const cardHeight = 360;
    const borderColor = selected ? 0xff8b5e : 0x344051;
    const borderWidth = selected ? 4 : 2;

    panel.add([
      this.scene.add.rectangle(x, cardY, width, cardHeight, selected ? 0x18202a : 0x141a22, 0.98).setOrigin(0),
      this.scene.add.rectangle(x, cardY, width, cardHeight).setOrigin(0).setStrokeStyle(borderWidth, borderColor, 1),
      this.scene.add
        .text(x + width / 2, cardY + 18, `dex ${asset.dex}`, textStyle("18px", "#9ad1ff"))
        .setOrigin(0.5, 0),
      this.scene.add.text(x + width / 2, cardY + 46, asset.name, textStyle("20px")).setOrigin(0.5, 0),
      this.scene.add
        .text(x + width / 2, cardY + 78, stageLabel, textStyle("16px", selected ? "#ffb18f" : "#9fb2c7"))
        .setOrigin(0.5, 0),
      this.scene.add
        .sprite(x + width / 2, cardY + 132, asset.iconKey, asset.iconFrame)
        .setScale(6)
        .setOrigin(0.5),
    ]);

    this.addPreviewSprite(panel, x + width / 2, cardY + 330, asset.frontKey, 7.2);
  }

  private getStageLabel(index: number, total: number): string {
    if (total <= 1) {
      return "Solo Stage";
    }
    if (index === 0) {
      return "Base Stage";
    }
    if (index === total - 1) {
      return "Final Stage";
    }
    return "Middle Stage";
  }

  private setControlsEnabled(enabled: boolean): void {
    this.controlsRoot.style.pointerEvents = enabled ? "auto" : "none";
    this.controlsRoot.style.opacity = enabled ? "1" : "0";
    this.controlsRoot.style.visibility = enabled ? "visible" : "hidden";
  }

  private suppressGameDataWrites(): void {
    if (this.gameDataOverrides) {
      return;
    }

    const gameData = this.scene.gameData as typeof this.scene.gameData & {
      setPokemonCaught: (...args: unknown[]) => Promise<unknown>;
      setPokemonSeen: (...args: unknown[]) => unknown;
      updateSpeciesDexIvs: (...args: unknown[]) => unknown;
    };

    this.gameDataOverrides = {
      setPokemonCaught: gameData.setPokemonCaught.bind(gameData),
      setPokemonSeen: gameData.setPokemonSeen.bind(gameData),
      updateSpeciesDexIvs: gameData.updateSpeciesDexIvs.bind(gameData),
    };

    gameData.setPokemonCaught = async () => false;
    gameData.setPokemonSeen = () => undefined;
    gameData.updateSpeciesDexIvs = () => undefined;
  }

  private restoreGameDataWrites(): void {
    if (!this.gameDataOverrides) {
      return;
    }

    const gameData = this.scene.gameData as typeof this.scene.gameData & {
      setPokemonCaught: (...args: unknown[]) => Promise<unknown>;
      setPokemonSeen: (...args: unknown[]) => unknown;
      updateSpeciesDexIvs: (...args: unknown[]) => unknown;
    };

    gameData.setPokemonCaught = this.gameDataOverrides.setPokemonCaught as typeof gameData.setPokemonCaught;
    gameData.setPokemonSeen = this.gameDataOverrides.setPokemonSeen as typeof gameData.setPokemonSeen;
    gameData.updateSpeciesDexIvs = this.gameDataOverrides.updateSpeciesDexIvs as typeof gameData.updateSpeciesDexIvs;
    this.gameDataOverrides = null;
  }

  private destroyEvolutionPokemon(): void {
    if (!this.activeEvolutionPokemon) {
      return;
    }

    this.activeEvolutionPokemon.destroy();
    this.activeEvolutionPokemon = null;
  }

  private startAutoAdvance(): void {
    this.stopAutoAdvance();
    this.autoAdvanceTimerId = window.setInterval(() => {
      if (!this.playingEvolutionScene) {
        return;
      }
      this.scene.ui.processInput(Button.ACTION);
    }, 450);
  }

  private stopAutoAdvance(): void {
    if (this.autoAdvanceTimerId == null) {
      return;
    }

    window.clearInterval(this.autoAdvanceTimerId);
    this.autoAdvanceTimerId = null;
  }

  private finishEvolutionScene(status: string): void {
    this.scene.phaseManager.clearPhaseQueue();
    this.stopAutoAdvance();
    this.restoreGameDataWrites();
    this.destroyEvolutionPokemon();
    this.playingEvolutionScene = false;
    this.root.setVisible(true);
    this.setControlsEnabled(true);
    this.statusText.setText(status);
  }

  private failEvolutionScene(message: string, error?: unknown): void {
    console.error("Maxx lab real scene failed", error ?? message);
    this.scene.phaseManager.clearPhaseQueue();
    this.stopAutoAdvance();
    this.restoreGameDataWrites();
    this.destroyEvolutionPokemon();
    this.playingEvolutionScene = false;
    this.root.setVisible(true);
    this.setControlsEnabled(true);
    this.statusText.setText(message);
  }

  private async playEvolution(): Promise<void> {
    if (this.playingEvolutionScene) {
      return;
    }

    if (!this.currentPreviewPair) {
      this.statusText.setText("No maxx step available for this family");
      return;
    }

    const { fromDex, toDex } = this.currentPreviewPair;
    const evolution = resolveEvolution(fromDex, toDex);
    if (!evolution) {
      this.statusText.setText(`No direct maxx path found for dex ${fromDex} -> ${toDex}`);
      return;
    }

    this.playingEvolutionScene = true;
    this.setControlsEnabled(false);
    this.root.setVisible(false);
    this.startAutoAdvance();

    try {
      const sourceSpecies = getPokemonSpecies(fromDex);
      let previewPokemon: PlayerPokemon;
      this.scene.debugAllowUnrosteredPlayerPokemon = true;
      try {
        previewPokemon = this.scene.addPlayerPokemon(sourceSpecies, Math.max(evolution.level, PREVIEW_LEVEL));
      } finally {
        this.scene.debugAllowUnrosteredPlayerPokemon = false;
      }
      previewPokemon.allowUnrosteredEvolution = true;
      previewPokemon.generateAndPopulateMoveset();
      previewPokemon.getLevelMoves = ((..._args) => []) as PlayerPokemon["getLevelMoves"];
      await previewPokemon.loadAssets();

      this.activeEvolutionPokemon = previewPokemon;
      this.suppressGameDataWrites();

      const status = `Played real maxx scene: ${getPokemonSpecies(fromDex).name} -> ${getPokemonSpecies(toDex).name}`;
      const returnPhase = new EvolutionLabReturnPhase(() => this.finishEvolutionScene(status));
      const evolutionPhase = this.scene.phaseManager.create(
        "EvolutionPhase",
        previewPokemon,
        evolution,
        previewPokemon.level - 1,
        false,
      );

      this.scene.phaseManager.clearAllPhases();
      this.scene.phaseManager.unshiftPhase(evolutionPhase);
      this.scene.phaseManager.pushPhase(returnPhase);
      this.scene.phaseManager.shiftPhase();
    } catch (error) {
      this.failEvolutionScene(`Maxx scene failed: ${error instanceof Error ? error.message : String(error)}`, error);
    }
  }

  private async render(): Promise<void> {
    const renderToken = ++this.renderToken;
    const dex = this.state.dex;
    this.statusText.setText(`Loading maxx family for dex ${dex}...`);
    this.content.removeAll(true);
    this.previewFromSprite = null;
    this.previewToSprite = null;
    this.previewFlash = null;
    this.previewFromLabel = null;
    this.previewToLabel = null;
    this.previewDirectionLabel = null;
    this.currentPreviewPair = null;

    let species: ReturnType<typeof getPokemonSpecies>;
    try {
      species = getPokemonSpecies(dex);
    } catch (error) {
      this.statusText.setText(String(error));
      return;
    }

    const familyDexes = getFamilyDexes(dex);
    this.currentFamilyDexes = familyDexes;
    const currentIndex = Math.max(0, familyDexes.indexOf(dex));
    this.currentPreviewPair = resolvePreviewPair(familyDexes, dex);
    this.subtitleText.setText(`family ${familyDexes.join(" -> ")} · focus ${species.name}`);

    try {
      const familyAssets = await loadFamilyAssets(this.scene, familyDexes);
      if (renderToken !== this.renderToken) {
        return;
      }

      const width = Number(this.scene.scale.width) || 1920;
      const familyPanel = this.addPanel(40, 118, width - 80, 430, "Family");
      const cardGap = 26;
      const cardWidth = Math.max(
        250,
        Math.min(360, (width - 80 - 40 - cardGap * (familyAssets.length - 1)) / familyAssets.length),
      );
      const totalFamilyWidth = familyAssets.length * cardWidth + (familyAssets.length - 1) * cardGap;
      const startX = Math.max(20, (width - 80 - totalFamilyWidth) / 2);

      familyAssets.forEach((asset, index) => {
        const x = startX + index * (cardWidth + cardGap);
        this.addFamilyStageCard(
          familyPanel,
          asset,
          x,
          cardWidth,
          asset.dex === dex,
          this.getStageLabel(index, familyAssets.length),
        );

        if (index < familyAssets.length - 1) {
          familyPanel.add(
            this.scene.add.text(x + cardWidth + 6, 240, "→", textStyle("42px", "#ffb18f")).setOrigin(0.5),
          );
        }
      });

      const previewPanel = this.addPanel(40, 580, width - 80, 380, "Maxx Scene");
      const previewPair = this.currentPreviewPair
        ? [
            familyAssets.find(asset => asset.dex === this.currentPreviewPair!.fromDex) ?? familyAssets[currentIndex],
            familyAssets.find(asset => asset.dex === this.currentPreviewPair!.toDex) ?? familyAssets[currentIndex],
          ]
        : [familyAssets[currentIndex], familyAssets[currentIndex]];

      const [fromAsset, toAsset] = previewPair;
      const fromX = Math.round((width - 80) * 0.31);
      const toX = Math.round((width - 80) * 0.69);
      const baseY = 338;

      previewPanel.add([
        this.scene.add.ellipse(fromX, 318, 220, 54, 0x171b23, 0.95),
        this.scene.add.ellipse(toX, 318, 220, 54, 0x171b23, 0.95),
      ]);

      this.previewFromLabel = this.scene.add
        .text(fromX, 76, `${fromAsset.name} · dex ${fromAsset.dex}`, textStyle("22px", "#8dc7ff"))
        .setOrigin(0.5, 0);
      this.previewToLabel = this.scene.add
        .text(toX, 76, `${toAsset.name} · dex ${toAsset.dex}`, textStyle("22px", "#7ff0b5"))
        .setOrigin(0.5, 0);
      this.previewDirectionLabel = this.scene.add
        .text((width - 80) / 2, 138, "Actual Maxx Phase Preview", textStyle("20px", "#c9d3df"))
        .setOrigin(0.5, 0);
      previewPanel.add([this.previewFromLabel, this.previewToLabel, this.previewDirectionLabel]);

      this.previewFromSprite = this.addPreviewSprite(previewPanel, fromX, baseY, fromAsset.frontKey, 10);
      this.previewToSprite = this.addPreviewSprite(previewPanel, toX, baseY, toAsset.frontKey, 10);
      this.previewToSprite.setAlpha(fromAsset.dex === toAsset.dex ? 1 : 0.35);

      this.previewFlash = this.scene.add
        .rectangle((width - 80) / 2, 210, width - 240, 240, 0xf6f2d8, 0.0)
        .setOrigin(0.5)
        .setBlendMode(Phaser.BlendModes.ADD);
      previewPanel.add(this.previewFlash);

      if (!this.currentPreviewPair) {
        this.statusText.setText("Solo-stage family loaded");
      } else if (fromAsset.dex === toAsset.dex) {
        this.statusText.setText("Final stage loaded");
      } else {
        this.statusText.setText("Maxx lab ready");
      }
    } catch (error) {
      console.error("Maxx lab render failed", error);
      this.statusText.setText(`Maxx lab failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  destroy(): void {
    this.stopAutoAdvance();
    this.restoreGameDataWrites();
    this.destroyEvolutionPokemon();
    this.controlsRoot.remove();
    this.root.destroy(true);
  }
}

export async function maybeStartEvolutionLab(scene: BattleScene): Promise<boolean> {
  const state = parseEvolutionLabState();
  if (!state) {
    return false;
  }

  writeEvolutionLabState(state);
  const lab = new EvolutionLab(scene, state);
  await lab.start();
  return true;
}
