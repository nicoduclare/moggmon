import { isGeneratedRosterSpeciesId } from "#constants/generated-roster";
import { expSpriteKeys } from "#sprites/sprite-keys";

const expKeyRegex = /^pkmn__?(back__)?(shiny__)?(female__)?(\d+)(-.*?)?(?:_[1-3])?$/;

export function hasExpSprite(key: string): boolean {
  const keyMatch = expKeyRegex.exec(key);
  if (!keyMatch) {
    return false;
  }

  const dex = Number.parseInt(keyMatch[4]!, 10);
  // Generated Mogger Mon entries should stay on the installed base atlases unless
  // matching exp atlases are intentionally authored for the same roster.
  if (isGeneratedRosterSpeciesId(dex)) {
    return false;
  }

  let k = keyMatch[4]!;
  if (keyMatch[2]) {
    k += "s";
  }
  if (keyMatch[1]) {
    k += "b";
  }
  if (keyMatch[3]) {
    k += "f";
  }
  if (keyMatch[5]) {
    k += keyMatch[5];
  }
  return expSpriteKeys.has(k);
}
