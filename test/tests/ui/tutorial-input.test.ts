import type { BattleScene } from "#app/battle-scene";
import { globalScene, initGlobalScene } from "#app/global-scene";
import { UiInputs } from "#app/ui-inputs";
import { Button } from "#enums/buttons";
import { AwaitableUiHandler } from "#ui/awaitable-ui-handler";
import type { UI } from "#ui/ui";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class TestAwaitableUiHandler extends AwaitableUiHandler {
  public readonly playSelect = vi.fn();

  setup(): void {}

  processInput(): boolean {
    return false;
  }

  override getUi(): UI {
    return { playSelect: this.playSelect } as unknown as UI;
  }

  primePrompt(callback = vi.fn()) {
    this.awaitingActionInput = true;
    this.onActionInput = callback;
    return callback;
  }

  isAwaitingActionInput(): boolean {
    return this.awaitingActionInput;
  }
}

describe("UI - Tutorial Input", () => {
  let handler: TestAwaitableUiHandler;
  let previousScene: BattleScene | undefined;

  beforeEach(() => {
    previousScene = globalScene;
    handler = new TestAwaitableUiHandler();
  });

  afterEach(() => {
    initGlobalScene(previousScene as BattleScene);
  });

  it.each([
    Button.ACTION,
    Button.CANCEL,
    Button.SUBMIT,
    Button.MENU,
  ])("should advance tutorial prompts from button %s", button => {
    const callback = handler.primePrompt();

    expect(handler.processTutorialInput(button)).toBe(true);
    expect(handler.playSelect).toHaveBeenCalledOnce();
    expect(callback).toHaveBeenCalledOnce();
    expect(handler.isAwaitingActionInput()).toBe(false);
  });

  it("should ignore non-prompt buttons", () => {
    const callback = handler.primePrompt();

    expect(handler.processTutorialInput(Button.UP)).toBe(false);
    expect(handler.playSelect).not.toHaveBeenCalled();
    expect(callback).not.toHaveBeenCalled();
    expect(handler.isAwaitingActionInput()).toBe(true);
  });

  it("should route menu input to active tutorials while the menu is disabled", () => {
    const processInput = vi.fn();
    handler.tutorialActive = true;
    initGlobalScene({
      disableMenu: true,
      ui: {
        getHandler: () => handler,
        processInput,
      },
    } as unknown as BattleScene);

    (Object.create(UiInputs.prototype) as UiInputs).buttonMenu();

    expect(processInput).toHaveBeenCalledExactlyOnceWith(Button.MENU);
  });

  it("should keep menu input blocked when no tutorial is active", () => {
    const processInput = vi.fn();
    handler.tutorialActive = false;
    initGlobalScene({
      disableMenu: true,
      ui: {
        getHandler: () => handler,
        processInput,
      },
    } as unknown as BattleScene);

    (Object.create(UiInputs.prototype) as UiInputs).buttonMenu();

    expect(processInput).not.toHaveBeenCalled();
  });
});
