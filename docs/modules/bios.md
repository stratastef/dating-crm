# Bios

Routes are in `app/bios.py`; the table is `bios` (one row per user and app). A bio is `{"bio": "...", "prompts": {"<prompt>": "<answer>"}}`.

| Route | Does |
| --- | --- |
| `POST /bios/{app}/rewrite` | Rewrite the bio in the body for that app from the style profile. Returns the rewrite and stores nothing. |
| `PUT /bios/{app}` | Store the version the user accepted for that app, replacing the previous one. |
| `GET /bios/{app}` | Read the accepted version. Empty until one is accepted. |

- To regenerate, call the rewrite route again. To regenerate from an edit, send the edited text as the body.
- The rewrite route returns `409` until the style profile is written, and `502` if Claude's reply is not a bio; the client can retry.
- Nothing is written to a dating app: in copilot the user copies the accepted text. Profile autopilot (the app changing a bio or photos in a dating app itself) is not built: no connector has a capability for it.
- `PUT /bios/{app}` writes an audit log entry: type `profile_change`, that app, target `bio`, trigger `copilot: user accepted a bio`. The text is not in the log.

## On the phone

**`BiosView`**: a segmented picker per dating app (`tinder`, `hinge`, `bumble`, the server's `DATING_APPS`), the accepted bio and prompts from `GET /bios/{app}` as fields, and "Rewrite in my voice". The rewrite shows under AI suggests, selectable for copying, with Accept (`PUT /bios/{app}`) and Rewrite again. A `409` (no style profile yet) shows a link to `VoiceView`. Nothing autosaves: what the user types is only sent to be rewritten, so leaving or switching app drops it. Prompts show in the order typed, or by their text after a load (`Bio.prompts` is a dictionary).
