# Battle AI Notes

The battle AI scores switch options and move targets from the active matchup, remaining HP, move legality, and battle context.

For launch work, treat this document as a high-level map rather than a full implementation spec. The inherited engine still has legacy class names internally; public UI should render those concepts as Mogger Mon, Mogmaster, and opponent/team language.

Current behavior to preserve:

- Opponents can switch when a bench member has a materially better matchup than the active battler.
- Boss-style encounters are allowed to switch more aggressively than ordinary encounters.
- Move choice weighs user benefit, target harm, type effectiveness, status value, setup value, and move availability.
- Randomness should keep battles from feeling solved while still avoiding obviously bad moves most of the time.

When changing AI, add a small scenario test or a Battle Lab repro link that demonstrates the behavior being adjusted.
