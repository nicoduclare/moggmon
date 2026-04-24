import type { BattleScene } from "#app/battle-scene";
import { isDev } from "#constants/app-constants";

const ENABLE_PARAM = "itemLab";
const QUERY_PARAM = "q";
const PAGE_PARAM = "page";
const FRAME_PARAM = "frame";
const ITEMS_TEXTURE_KEY = "items";

type ItemLabState = {
  query: string;
  page: number;
  selectedFrame: string | null;
};

function parseItemLabState(): ItemLabState | null {
  if (!isDev) {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get(ENABLE_PARAM) !== "1") {
    return null;
  }

  const rawPage = Number.parseInt(params.get(PAGE_PARAM) || "1", 10);
  return {
    query: (params.get(QUERY_PARAM) || "").trim(),
    page: Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1,
    selectedFrame: params.get(FRAME_PARAM),
  };
}

function writeItemLabState(state: ItemLabState): void {
  const url = new URL(window.location.href);
  url.searchParams.set(ENABLE_PARAM, "1");
  url.searchParams.set(PAGE_PARAM, String(state.page));

  if (state.query) {
    url.searchParams.set(QUERY_PARAM, state.query);
  } else {
    url.searchParams.delete(QUERY_PARAM);
  }

  if (state.selectedFrame) {
    url.searchParams.set(FRAME_PARAM, state.selectedFrame);
  } else {
    url.searchParams.delete(FRAME_PARAM);
  }

  window.history.replaceState({}, "", url);
}

function textStyle(fontSize: string, color = "#f7f7f7"): Phaser.Types.GameObjects.Text.TextStyle {
  return {
    fontFamily: "emerald",
    fontSize,
    color,
  };
}

function titleCase(value: string): string {
  return value.replace(/\b\w/g, character => character.toUpperCase());
}

function formatFrameName(frame: string): string {
  const cryoNames: Record<string, string> = {
    pb: "Cryo Tank",
    pb_gold: "Gold Cryo Tank",
    pb_silver: "Silver Cryo Tank",
    gb: "Deep Cryo Tank",
    rb: "Rogue Cryo Tank",
    ub: "Ultra Cryo Tank",
    mb: "Master Cryo Tank",
    strange_ball: "Strange Cryo Core",
    lock_capsule: "Cryo Lockbox",
    lure: "Cryo Lure",
    super_lure: "Super Cryo Lure",
    max_lure: "Max Cryo Lure",
    golden_net: "Gold Capture Net",
    catching_charm: "Capture Charm",
  };

  if (cryoNames[frame]) {
    return cryoNames[frame];
  }

  if (frame.startsWith("tm_")) {
    return `${titleCase(frame.slice(3).replace(/[_-]/g, " "))} BrainDance`;
  }

  if (frame.endsWith("_memory")) {
    return `${titleCase(frame.replace(/_memory$/, "").replace(/[_-]/g, " "))} BrainDance Memory`;
  }

  if (frame.endsWith("_drive") || frame === "dubious_disc" || frame === "upgrade") {
    return `${titleCase(frame.replace(/[_-]/g, " "))} BrainDance Media`;
  }

  return frame
    .replace(/berry_juice_bad/g, "foul zaza vial")
    .replace(/berry_juice_good/g, "bright zaza vial")
    .replace(/berry_pouch/g, "zaza stash")
    .replace(/berry_pot/g, "zaza grow pot")
    .replace(/berry_sweet/g, "zaza sweet")
    .replace(/strawberry_sweet/g, "zaza sweet")
    .replace(/_berry\b/g, " zaza")
    .replace(/\bberry\b/g, "zaza")
    .replace(/\bmushroom(s?)\b/g, "shroom$1")
    .replace(/[_-]/g, " ");
}

class ItemLab {
  private readonly scene: BattleScene;
  private readonly root: Phaser.GameObjects.Container;
  private readonly content: Phaser.GameObjects.Container;
  private readonly titleText: Phaser.GameObjects.Text;
  private readonly statusText: Phaser.GameObjects.Text;
  private readonly controlsRoot: HTMLDivElement;
  private readonly searchInput: HTMLInputElement;
  private readonly keyboardHandler: (event: KeyboardEvent) => void;
  private state: ItemLabState;

  constructor(scene: BattleScene, state: ItemLabState) {
    this.scene = scene;
    this.state = state;

    const width = Number(scene.scale.width) || 1920;
    const height = Number(scene.scale.height) || 1080;

    this.root = scene.add.container(0, 0).setDepth(1000);
    this.root.add([
      scene.add.rectangle(0, 0, width, height, 0x0d1319, 0.98).setOrigin(0),
      scene.add.text(48, 28, "Mogger Mon Item Lab", textStyle("46px")),
      scene.add.text(48, 82, "", textStyle("22px", "#a8c7dd")),
      scene.add.text(48, height - 42, "", textStyle("20px", "#9ad1ff")),
    ]);

    this.titleText = this.root.list[2] as Phaser.GameObjects.Text;
    this.statusText = this.root.list[3] as Phaser.GameObjects.Text;
    this.content = scene.add.container(0, 0);
    this.root.add(this.content);

    const controls = this.createControls();
    this.controlsRoot = controls.root;
    this.searchInput = controls.searchInput;
    this.keyboardHandler = event => this.handleKeyboardNavigation(event);
    document.addEventListener("keydown", this.keyboardHandler);
    scene.events.once(Phaser.Scenes.Events.DESTROY, () => this.destroy());
  }

  async start(): Promise<void> {
    this.render();
  }

  private createControls(): { root: HTMLDivElement; searchInput: HTMLInputElement } {
    const root = document.createElement("div");
    root.dataset.testid = "item-lab-controls";
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
      fontSize: "14px",
      color: "#f7f7f7",
    } satisfies Partial<CSSStyleDeclaration>);

    const label = document.createElement("span");
    label.textContent = "Items";
    root.append(label);

    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Search item frames";
    searchInput.value = this.state.query;
    searchInput.dataset.testid = "item-lab-search-input";
    Object.assign(searchInput.style, {
      width: "220px",
      padding: "6px 8px",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.18)",
      background: "rgba(255,255,255,0.08)",
      color: "#f7f7f7",
      fontSize: "14px",
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
        fontSize: "14px",
        cursor: "pointer",
      } satisfies Partial<CSSStyleDeclaration>);
      button.onclick = handler;
      root.append(button);
    };

    attachButton("Prev", () => this.selectPage(this.state.page - 1), "item-lab-prev");
    attachButton("Next", () => this.selectPage(this.state.page + 1), "item-lab-next");
    attachButton("Archive", () => this.openRoute({ pokedex: "1", dex: "1" }), "item-lab-archive");

    searchInput.addEventListener("input", () => {
      this.setState({
        query: searchInput.value.trim(),
        page: 1,
        selectedFrame: null,
      });
    });

    document.body.append(root);
    return { root, searchInput };
  }

  private openRoute(params: Record<string, string>): void {
    const url = new URL(window.location.href);
    for (const key of [
      ENABLE_PARAM,
      QUERY_PARAM,
      PAGE_PARAM,
      FRAME_PARAM,
      "battleLab",
      "moveLab",
      "spriteLab",
      "evolutionLab",
      "pokedex",
      "pokedexLab",
      "archiveLab",
    ]) {
      url.searchParams.delete(key);
    }
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
    window.location.assign(url.toString());
  }

  private getFrameNames(): string[] {
    if (!this.scene.textures.exists(ITEMS_TEXTURE_KEY)) {
      return [];
    }

    return this.scene.textures
      .get(ITEMS_TEXTURE_KEY)
      .getFrameNames(false)
      .filter(frame => frame !== "__BASE")
      .sort((left, right) => left.localeCompare(right));
  }

  private getFilteredFrames(): string[] {
    const normalizedQuery = this.state.query.toLowerCase();
    const frames = this.getFrameNames();
    if (!normalizedQuery) {
      return frames;
    }

    return frames.filter(
      frame =>
        frame.toLowerCase().includes(normalizedQuery) || formatFrameName(frame).toLowerCase().includes(normalizedQuery),
    );
  }

  private getLayout(): { columns: number; rows: number; pageSize: number; cellWidth: number; cellHeight: number } {
    const width = Number(this.scene.scale.width) || 1920;
    const height = Number(this.scene.scale.height) || 1080;
    const cellWidth = width < 1000 ? 112 : 140;
    const cellHeight = 118;
    const columns = Math.max(3, Math.floor((width - 360) / cellWidth));
    const rows = Math.max(2, Math.floor((height - 230) / cellHeight));
    return {
      columns,
      rows,
      pageSize: columns * rows,
      cellWidth,
      cellHeight,
    };
  }

  private setState(patch: Partial<ItemLabState>): void {
    this.state = {
      ...this.state,
      ...patch,
    };
    if (this.searchInput.value !== this.state.query) {
      this.searchInput.value = this.state.query;
    }
    this.render();
  }

  private selectPage(page: number): void {
    const frames = this.getFilteredFrames();
    const layout = this.getLayout();
    const pageCount = Math.max(1, Math.ceil(frames.length / layout.pageSize));
    const nextPage = Phaser.Math.Clamp(page, 1, pageCount);
    this.setState({
      page: nextPage,
      selectedFrame: frames[(nextPage - 1) * layout.pageSize] ?? null,
    });
  }

  private selectRelative(delta: number): void {
    const frames = this.getFilteredFrames();
    if (frames.length === 0) {
      return;
    }

    const layout = this.getLayout();
    const currentIndex = Math.max(0, this.state.selectedFrame ? frames.indexOf(this.state.selectedFrame) : 0);
    const nextIndex = Phaser.Math.Wrap(currentIndex + delta, 0, frames.length);
    this.setState({
      page: Math.floor(nextIndex / layout.pageSize) + 1,
      selectedFrame: frames[nextIndex],
    });
  }

  private handleKeyboardNavigation(event: KeyboardEvent): void {
    if (event.target instanceof HTMLInputElement) {
      return;
    }

    const layout = this.getLayout();
    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        this.selectRelative(-1);
        break;
      case "ArrowRight":
        event.preventDefault();
        this.selectRelative(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        this.selectRelative(-layout.columns);
        break;
      case "ArrowDown":
        event.preventDefault();
        this.selectRelative(layout.columns);
        break;
      case "PageUp":
        event.preventDefault();
        this.selectPage(this.state.page - 1);
        break;
      case "PageDown":
        event.preventDefault();
        this.selectPage(this.state.page + 1);
        break;
      default:
        break;
    }
  }

  private render(): void {
    this.content.removeAll(true);

    const frames = this.getFilteredFrames();
    const layout = this.getLayout();
    const pageCount = Math.max(1, Math.ceil(frames.length / layout.pageSize));
    this.state.page = Phaser.Math.Clamp(this.state.page, 1, pageCount);

    const pageStart = (this.state.page - 1) * layout.pageSize;
    const pageFrames = frames.slice(pageStart, pageStart + layout.pageSize);
    if (!this.state.selectedFrame || !frames.includes(this.state.selectedFrame)) {
      this.state.selectedFrame = pageFrames[0] ?? null;
    }
    writeItemLabState(this.state);

    const width = Number(this.scene.scale.width) || 1920;
    const height = Number(this.scene.scale.height) || 1080;
    this.titleText.setText(`${frames.length} item atlas frames · page ${this.state.page}/${pageCount}`);
    this.statusText.setText("Arrows select · PageUp/PageDown paginate · Search filters runtime items atlas");

    const gridX = 48;
    const gridY = 136;
    const detailX = width - 286;
    const detailWidth = 238;
    const gridWidth = Math.max(220, detailX - gridX - 34);
    this.content.add([
      this.scene.add.rectangle(gridX - 14, gridY - 18, gridWidth, height - gridY - 58, 0x131c25, 0.92).setOrigin(0),
      this.scene.add
        .rectangle(gridX - 14, gridY - 18, gridWidth, height - gridY - 58)
        .setOrigin(0)
        .setStrokeStyle(2, 0x315064),
      this.scene.add.rectangle(detailX, gridY - 18, detailWidth, height - gridY - 58, 0x111820, 0.96).setOrigin(0),
      this.scene.add
        .rectangle(detailX, gridY - 18, detailWidth, height - gridY - 58)
        .setOrigin(0)
        .setStrokeStyle(2, 0x4d6674),
    ]);

    for (const [index, frame] of pageFrames.entries()) {
      const column = index % layout.columns;
      const row = Math.floor(index / layout.columns);
      const x = gridX + column * layout.cellWidth;
      const y = gridY + row * layout.cellHeight;
      const selected = frame === this.state.selectedFrame;
      const background = this.scene.add
        .rectangle(
          x,
          y,
          layout.cellWidth - 12,
          layout.cellHeight - 12,
          selected ? 0x27445a : 0x182530,
          selected ? 0.98 : 0.88,
        )
        .setOrigin(0)
        .setStrokeStyle(selected ? 3 : 1, selected ? 0xffc46b : 0x355160);
      background.setInteractive({ useHandCursor: true });
      background.on("pointerdown", () => this.setState({ selectedFrame: frame }));

      const icon = this.scene.add.sprite(x + layout.cellWidth / 2 - 6, y + 36, ITEMS_TEXTURE_KEY, frame).setScale(2);
      const label = this.scene.add
        .text(x + 8, y + 74, formatFrameName(frame), textStyle("15px", selected ? "#ffe0a3" : "#c9d7e0"))
        .setWordWrapWidth(layout.cellWidth - 26, true)
        .setMaxLines(2);
      this.content.add([background, icon, label]);
    }

    this.renderSelectedFrame(detailX, gridY, detailWidth);
  }

  private renderSelectedFrame(detailX: number, gridY: number, detailWidth: number): void {
    const frame = this.state.selectedFrame;
    if (!frame) {
      this.content.add(
        this.scene.add.text(detailX + 24, gridY + 24, "No item frames found", textStyle("24px", "#ffb0a8")),
      );
      return;
    }

    const detailCenterX = detailX + detailWidth / 2;
    const textureFrame = this.scene.textures.getFrame(ITEMS_TEXTURE_KEY, frame);
    const sourceWidth = textureFrame?.width ?? 32;
    const sourceHeight = textureFrame?.height ?? 32;
    const scale = Math.min(6, Math.max(3, Math.floor(170 / Math.max(sourceWidth, sourceHeight))));

    this.content.add([
      this.scene.add.text(detailX + 18, gridY + 8, "Selected", textStyle("22px", "#9ad1ff")),
      this.scene.add
        .text(detailX + 18, gridY + 42, formatFrameName(frame), textStyle("20px", "#f7f7f7"))
        .setWordWrapWidth(detailWidth - 36, true),
      this.scene.add.rectangle(detailCenterX - 88, gridY + 124, 176, 176, 0x0a0f14, 0.78).setOrigin(0),
      this.scene.add
        .rectangle(detailCenterX - 88, gridY + 124, 176, 176)
        .setOrigin(0)
        .setStrokeStyle(1, 0x546d7c),
      this.scene.add.sprite(detailCenterX, gridY + 212, ITEMS_TEXTURE_KEY, frame).setScale(scale),
      this.scene.add
        .text(detailX + 18, gridY + 326, `Label: ${formatFrameName(frame)}`, textStyle("17px", "#c7d8e2"))
        .setWordWrapWidth(detailWidth - 36, true),
      this.scene.add.text(
        detailX + 18,
        gridY + 398,
        `${sourceWidth}x${sourceHeight} source`,
        textStyle("17px", "#8fa8b8"),
      ),
    ]);
  }

  destroy(): void {
    document.removeEventListener("keydown", this.keyboardHandler);
    this.controlsRoot.remove();
    this.root.destroy(true);
  }
}

export async function maybeStartItemLab(scene: BattleScene): Promise<boolean> {
  const state = parseItemLabState();
  if (!state) {
    return false;
  }

  writeItemLabState(state);
  const lab = new ItemLab(scene, state);
  await lab.start();
  return true;
}
