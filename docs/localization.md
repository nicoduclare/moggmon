# Localization

Mogger Mon currently launches with English as the only selectable language.

The `locales` directory is a submodule and can still carry inherited locale structure, but public launch copy should be reviewed in English first and then translated from the Mogger Mon source text. Do not translate from older upstream strings if the wording has been rethemed.

Recommended workflow:

1. Add or update English keys in `locales/en`.
2. Run the UI in development mode and verify the visible text in context.
3. Only then fan out translations to other locale folders.
4. Keep gameplay terms consistent: Mogger Mon, Mogmaster, Archive, Maxx, Cryotank, BrainDance, Zaza, and Pod.

If a locale has not been reviewed, hide it from the launch language selector instead of shipping mixed terminology.

The launch selector is intentionally limited to English in `src/plugins/i18n.ts` and `src/system/settings/settings-language.ts` until the inherited translation folders are fully rethemed.
