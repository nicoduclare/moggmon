import type { BattleScene } from "#app/battle-scene";
import { isDev } from "#constants/app-constants";
import { getCachedUrl } from "#utils/fetch-utils";
import { getPokemonSpecies } from "#utils/pokemon-utils";

const ENABLE_PARAM = "spriteLab";
const DEX_PARAM = "dex";

type SpriteLabState = {
  dex: number;
};

type LoadedSpeciesAssets = {
  currentFrontKey: string;
  currentBackKey: string;
  currentIconKey: string;
  currentIconFrame: string;
  backupFrontKey: string | null;
  backupBackKey: string | null;
  backupIconKey: string | null;
};

type AtlasMetrics = {
  averageWidth: number;
  averageHeight: number;
  maxWidth: number;
  maxHeight: number;
  frameCount: number;
};

function parseSpriteLabState(): SpriteLabState | null {
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

function writeSpriteLabState(state: SpriteLabState): void {
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

async function urlExists(path: string): Promise<boolean> {
  try {
    const response = await fetch(getCachedUrl(path), { method: "HEAD" });
    return response.ok;
  } catch {
    return false;
  }
}

async function loadAtlasMetrics(path: string): Promise<AtlasMetrics | null> {
  try {
    const response = await fetch(getCachedUrl(path));
    if (!response.ok) {
      return null;
    }
    const data = await response.json();
    const frames = data?.textures?.[0]?.frames;
    if (!Array.isArray(frames) || frames.length === 0) {
      return null;
    }

    const widths = frames.map((frame: { spriteSourceSize: { w: number } }) => frame.spriteSourceSize.w);
    const heights = frames.map((frame: { spriteSourceSize: { h: number } }) => frame.spriteSourceSize.h);
    return {
      averageWidth: widths.reduce((sum, width) => sum + width, 0) / widths.length,
      averageHeight: heights.reduce((sum, height) => sum + height, 0) / heights.length,
      maxWidth: Math.max(...widths),
      maxHeight: Math.max(...heights),
      frameCount: frames.length,
    };
  } catch {
    return null;
  }
}

function formatMetrics(metrics: AtlasMetrics | null): string {
  if (!metrics) {
    return "missing";
  }
  return [
    `${metrics.averageWidth.toFixed(1)}x${metrics.averageHeight.toFixed(1)} avg`,
    `${metrics.maxWidth}x${metrics.maxHeight} max`,
    `${metrics.frameCount} frames`,
  ].join(" · ");
}

async function queueAndLoadAtlases(
  scene: BattleScene,
  atlases: Array<{ key: string; pngPath: string; jsonPath: string }>,
): Promise<void> {
  const missing = atlases.filter(a => !scene.textures.exists(a.key));
  if (missing.length === 0) {
    return;
  }

  for (const atlas of missing) {
    scene.load.atlas(atlas.key, getCachedUrl(atlas.pngPath), getCachedUrl(atlas.jsonPath));
  }

  await new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      scene.load.off(Phaser.Loader.Events.COMPLETE, onComplete);
      scene.load.off(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
    };
    const onComplete = () => {
      cleanup();
      resolve();
    };
    const onError = (file: Phaser.Loader.File) => {
      cleanup();
      reject(new Error(`Failed loading sprite lab asset: ${file.key}`));
    };

    scene.load.once(Phaser.Loader.Events.COMPLETE, onComplete);
    scene.load.once(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
    scene.load.start();
  });
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

  scene.anims.create({
    key,
    frames: frameNames,
    frameRate: 10,
    repeat: -1,
  });
}

class SpriteLab {
  private readonly scene: BattleScene;
  private state: SpriteLabState;
  private readonly root: Phaser.GameObjects.Container;
  private readonly content: Phaser.GameObjects.Container;
  private readonly statusText: Phaser.GameObjects.Text;
  private readonly titleText: Phaser.GameObjects.Text;
  private readonly subtitleText: Phaser.GameObjects.Text;
  private readonly controlsRoot: HTMLDivElement;
  private readonly metricsRoot: HTMLPreElement;
  private renderToken = 0;

  constructor(scene: BattleScene, state: SpriteLabState) {
    this.scene = scene;
    this.state = state;

    this.root = scene.add.container(0, 0).setDepth(1000);
    this.content = scene.add.container(0, 0);
    this.root.add(this.content);

    this.titleText = scene.add.text(48, 30, "Mogger Mon Sprite Lab", textStyle("48px"));
    this.subtitleText = scene.add.text(48, 82, "", textStyle("24px", "#a9b4c1"));
    this.statusText = scene.add.text(48, 1020, "", textStyle("20px", "#9ad1ff"));
    this.root.add([this.titleText, this.subtitleText, this.statusText]);

    this.controlsRoot = this.createControls();
    this.metricsRoot = this.createMetricsPanel();
    scene.events.once(Phaser.Scenes.Events.DESTROY, () => this.destroy());
  }

  async start(): Promise<void> {
    await this.render();
  }

  private createControls(): HTMLDivElement {
    const root = document.createElement("div");
    root.dataset.testid = "sprite-lab-controls";
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
    input.dataset.testid = "sprite-lab-dex-input";
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
      writeSpriteLabState(this.state);
      void this.render();
    };

    attachButton("Prev", () => setDex(this.state.dex - 1), "sprite-lab-prev");
    attachButton("Next", () => setDex(this.state.dex + 1), "sprite-lab-next");
    attachButton("Go", () => setDex(Number.parseInt(input.value || "1", 10)), "sprite-lab-go");

    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        setDex(Number.parseInt(input.value || "1", 10));
      }
    });

    document.body.append(root);

    (window as Window & { __MOGGER_MON_SPRITE_LAB__?: unknown }).__MOGGER_MON_SPRITE_LAB__ = {
      setDex,
      rerender: () => this.render(),
    };

    return root;
  }

  private createMetricsPanel(): HTMLPreElement {
    const root = document.createElement("pre");
    root.dataset.testid = "sprite-lab-metrics";
    Object.assign(root.style, {
      position: "fixed",
      top: "76px",
      right: "16px",
      zIndex: "9999",
      width: "360px",
      margin: "0",
      padding: "10px 12px",
      borderRadius: "12px",
      background: "rgba(12, 15, 20, 0.92)",
      border: "1px solid rgba(255,255,255,0.12)",
      fontFamily: "monospace",
      fontSize: "12px",
      lineHeight: "1.45",
      whiteSpace: "pre-wrap",
      color: "#cfe5ff",
    } satisfies Partial<CSSStyleDeclaration>);
    root.textContent = "Loading sprite metrics...";
    document.body.append(root);
    return root;
  }

  private async loadSpeciesAssets(speciesId: number): Promise<LoadedSpeciesAssets> {
    const species = getPokemonSpecies(speciesId);
    const currentIconKey = species.getIconAtlasKey(0, false, 0);
    const currentIconFrame = species.getIconId(false, 0, false, 0);

    await species.loadAssets(false, 0, false, 0, true, false);
    await species.loadAssets(false, 0, false, 0, true, true);

    const backupFrontKey = `sprite_lab_backup_front_${speciesId}`;
    const backupBackKey = `sprite_lab_backup_back_${speciesId}`;
    const iconSheetKey = currentIconKey;
    const iconSheetSuffix = iconSheetKey.replace("pokemon_icons_", "");
    const backupIconKey = `sprite_lab_backup_icon_${iconSheetSuffix}`;

    const atlasesToLoad: Array<{ key: string; pngPath: string; jsonPath: string }> = [];

    if (await urlExists(`images/pokemon/_backup/${speciesId}.png`)) {
      atlasesToLoad.push({
        key: backupFrontKey,
        pngPath: `images/pokemon/_backup/${speciesId}.png`,
        jsonPath: `images/pokemon/_backup/${speciesId}.json`,
      });
    }

    if (await urlExists(`images/pokemon/_backup/back/${speciesId}.png`)) {
      atlasesToLoad.push({
        key: backupBackKey,
        pngPath: `images/pokemon/_backup/back/${speciesId}.png`,
        jsonPath: `images/pokemon/_backup/back/${speciesId}.json`,
      });
    }

    if (await urlExists(`images/${iconSheetKey}.backup.png`)) {
      atlasesToLoad.push({
        key: backupIconKey,
        pngPath: `images/${iconSheetKey}.backup.png`,
        jsonPath: `images/${iconSheetKey}.json`,
      });
    }

    await queueAndLoadAtlases(this.scene, atlasesToLoad);

    if (this.scene.textures.exists(backupFrontKey)) {
      ensureLoopingAnimation(this.scene, backupFrontKey);
    }
    if (this.scene.textures.exists(backupBackKey)) {
      ensureLoopingAnimation(this.scene, backupBackKey);
    }

    return {
      currentFrontKey: species.getSpriteKey(false, 0, false, 0, false),
      currentBackKey: species.getSpriteKey(false, 0, false, 0, true),
      currentIconKey,
      currentIconFrame,
      backupFrontKey: this.scene.textures.exists(backupFrontKey) ? backupFrontKey : null,
      backupBackKey: this.scene.textures.exists(backupBackKey) ? backupBackKey : null,
      backupIconKey: this.scene.textures.exists(backupIconKey) ? backupIconKey : null,
    };
  }

  private addPanel(x: number, y: number, width: number, height: number, title: string): Phaser.GameObjects.Container {
    const panel = this.scene.add.container(x, y);
    const bg = this.scene.add.rectangle(0, 0, width, height, 0x10151d, 0.95).setOrigin(0);
    const border = this.scene.add.rectangle(0, 0, width, height).setOrigin(0).setStrokeStyle(2, 0x344051, 1);
    const heading = this.scene.add.text(20, 16, title, textStyle("28px"));
    panel.add([bg, border, heading]);
    this.content.add(panel);
    return panel;
  }

  private addCompareLabels(panel: Phaser.GameObjects.Container, leftX: number, rightX: number): void {
    panel.add([
      this.scene.add.text(leftX, 48, "Original", textStyle("20px", "#8dc7ff")),
      this.scene.add.text(rightX, 48, "Current", textStyle("20px", "#7ff0b5")),
    ]);
  }

  private addPreviewSprite(
    panel: Phaser.GameObjects.Container,
    x: number,
    y: number,
    key: string | null,
    scale: number,
    originX = 0.5,
    originY = 1,
  ): Phaser.GameObjects.Text | Phaser.GameObjects.Sprite {
    if (!key) {
      const missing = this.scene.add.text(x, y, "missing", textStyle("18px", "#ff8d8d")).setOrigin(0.5, 1);
      panel.add(missing);
      return missing;
    }

    const sprite = this.scene.add.sprite(x, y, key).setOrigin(originX, originY).setScale(scale);
    const texture = this.scene.textures.get(key);
    if (texture.has("0001.png")) {
      sprite.setFrame("0001.png");
    } else if (this.scene.anims.exists(key)) {
      sprite.play(key);
    }
    panel.add(sprite);
    return sprite;
  }

  private addIconSprite(
    panel: Phaser.GameObjects.Container,
    x: number,
    y: number,
    key: string | null,
    frame: string,
    scale: number,
  ): Phaser.GameObjects.Text | Phaser.GameObjects.Sprite {
    if (!key) {
      const missing = this.scene.add.text(x, y, "missing", textStyle("18px", "#ff8d8d")).setOrigin(0.5);
      panel.add(missing);
      return missing;
    }

    const sprite = this.scene.add.sprite(x, y, key, frame).setScale(scale).setOrigin(0.5);
    panel.add(sprite);
    return sprite;
  }

  private async render(): Promise<void> {
    const renderToken = ++this.renderToken;
    const dex = this.state.dex;
    this.statusText.setText(`Loading dex ${dex}...`);
    this.metricsRoot.textContent = "Loading sprite metrics...";
    this.content.removeAll(true);

    let species: ReturnType<typeof getPokemonSpecies>;
    try {
      species = getPokemonSpecies(dex);
      if (!species) {
        throw new Error(`No species found for dex ${dex}`);
      }
    } catch (error) {
      this.statusText.setText(String(error));
      return;
    }

    this.subtitleText.setText(`dex ${dex} · ${species.name}`);

    try {
      const assets = await this.loadSpeciesAssets(dex);
      if (renderToken !== this.renderToken) {
        return;
      }

      const [backupFrontMetrics, currentFrontMetrics, backupBackMetrics, currentBackMetrics] = await Promise.all([
        loadAtlasMetrics(`images/pokemon/_backup/${dex}.json`),
        loadAtlasMetrics(`images/pokemon/${dex}.json`),
        loadAtlasMetrics(`images/pokemon/_backup/back/${dex}.json`),
        loadAtlasMetrics(`images/pokemon/back/${dex}.json`),
      ]);
      if (renderToken !== this.renderToken) {
        return;
      }
      this.metricsRoot.textContent = [
        `dex ${dex} · ${species.name}`,
        `front original: ${formatMetrics(backupFrontMetrics)}`,
        `front current:  ${formatMetrics(currentFrontMetrics)}`,
        `back original:  ${formatMetrics(backupBackMetrics)}`,
        `back current:   ${formatMetrics(currentBackMetrics)}`,
      ].join("\n");

      const boxPanel = this.addPanel(40, 120, 560, 330, "Box");
      boxPanel.setName("sprite-lab-box");
      this.addCompareLabels(boxPanel, 70, 340);
      this.addIconSprite(boxPanel, 150, 120, assets.backupIconKey, assets.currentIconFrame, 6);
      this.addIconSprite(boxPanel, 420, 120, assets.currentIconKey, assets.currentIconFrame, 6);
      this.addPreviewSprite(boxPanel, 150, 290, assets.backupFrontKey, 5.5);
      this.addPreviewSprite(boxPanel, 420, 290, assets.currentFrontKey, 5.5);

      const battlePanel = this.addPanel(640, 120, 1240, 330, "Battle");
      battlePanel.setName("sprite-lab-battle");
      this.addCompareLabels(battlePanel, 110, 720);
      battlePanel.add([
        this.scene.add.ellipse(270, 268, 180, 42, 0x171b23, 0.95),
        this.scene.add.ellipse(470, 172, 180, 42, 0x171b23, 0.95),
        this.scene.add.ellipse(880, 268, 180, 42, 0x171b23, 0.95),
        this.scene.add.ellipse(1080, 172, 180, 42, 0x171b23, 0.95),
        this.scene.add.text(120, 286, "player back", textStyle("16px", "#93a1b3")),
        this.scene.add.text(390, 190, "enemy front", textStyle("16px", "#93a1b3")),
        this.scene.add.text(730, 286, "player back", textStyle("16px", "#93a1b3")),
        this.scene.add.text(1000, 190, "enemy front", textStyle("16px", "#93a1b3")),
      ]);
      this.addPreviewSprite(battlePanel, 270, 260, assets.backupBackKey, 5.5);
      this.addPreviewSprite(battlePanel, 470, 165, assets.backupFrontKey, 5.5);
      this.addPreviewSprite(battlePanel, 880, 260, assets.currentBackKey, 5.5);
      this.addPreviewSprite(battlePanel, 1080, 165, assets.currentFrontKey, 5.5);

      const evolutionPanel = this.addPanel(40, 480, 1840, 500, "Maxx");
      evolutionPanel.setName("sprite-lab-evolution");
      this.addCompareLabels(evolutionPanel, 140, 1040);
      evolutionPanel.add([
        this.scene.add.text(250, 88, species.name, textStyle("18px", "#cfd6df")).setOrigin(0.5, 0),
        this.scene.add.text(1150, 88, species.name, textStyle("18px", "#cfd6df")).setOrigin(0.5, 0),
      ]);
      this.addPreviewSprite(evolutionPanel, 250, 430, assets.backupFrontKey, 9);
      this.addPreviewSprite(evolutionPanel, 1150, 430, assets.currentFrontKey, 9);

      this.statusText.setText("Sprite lab ready");
    } catch (error) {
      console.error("Sprite lab render failed", error);
      this.statusText.setText(`Sprite lab failed: ${error instanceof Error ? error.message : String(error)}`);
      this.metricsRoot.textContent = `Sprite lab failed: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  destroy(): void {
    this.controlsRoot.remove();
    this.metricsRoot.remove();
    this.root.destroy(true);
    (window as Window & { __MOGGER_MON_SPRITE_LAB__?: unknown }).__MOGGER_MON_SPRITE_LAB__ = undefined;
  }
}

export async function maybeStartSpriteLab(scene: BattleScene): Promise<boolean> {
  const state = parseSpriteLabState();
  if (!state) {
    return false;
  }

  writeSpriteLabState(state);
  const lab = new SpriteLab(scene, state);
  await lab.start();
  return true;
}
