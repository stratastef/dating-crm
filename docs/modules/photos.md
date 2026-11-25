# Photos

Routes are in `app/photos.py`; the table is `photos` (one row per photo). A photo is `{"id", "rank", "reason", "suggested_edit", "edit"}`.

| Route | Does |
| --- | --- |
| `POST /photos` | Store one photo. The body is the file itself, with `Content-Type: image/jpeg` or `image/png`. |
| `GET /photos` | List the photos, best first. Unranked photos come last. |
| `POST /photos/rank` | Have Claude look at all the photos and store a `rank` (1 is best) and a `reason` for each. It may also offer a light edit per photo, stored as `suggested_edit`. |
| `GET /photos/{id}/preview` | The photo with the edit on offer applied. Stores nothing. |
| `PUT /photos/{id}/edit` with `{"accept": true}` | Accept or reject the edit on offer. An accepted edit becomes `edit`; either way `suggested_edit` is cleared. |
| `GET /photos/{id}/image` | The photo with the accepted edit applied, or the file as uploaded. |

- **Files** are on local disk under `PHOTOS_DIR` (default `./photos`), as `<user id>/<photo id>`. Compose sets it to `/data/photos` on the `photos` volume, shared by the API and worker. Back that volume up with the database. The uploaded file is never changed or deleted.
- **Upload limits:** at most 10 MB (`413`), `image/jpeg` or `image/png` only (`415`), and the file must really be that type (`422`).
- **Edits are not generated.** An edit is `{"crop": [left, top, right, bottom] or null, "exposure", "colour"}`: crop in fractions of the width and height, the two factors from 0.5 to 1.5 where 1 changes nothing. Claude only proposes these numbers. `_edited()` applies them to the uploaded file with Pillow. No route returns pixels from a model.
- Claude is called with the photos through `llm.call(..., images=[(content_type, data)])`. Each photo is sent scaled down to 1024 pixels a side.
- The rank route returns `409` when the user has no photos, and `502` when Claude's reply does not rank exactly the user's photos or holds an edit outside the limits; nothing is stored then.
- Nothing is uploaded to a dating app and nothing rotates photos: the user saves the photo they want and changes their profile themselves.
- Accepting an edit writes an audit log entry: type `profile_change`, app `all` (a photo belongs to no one dating app), target `photo:<photos.id>`, trigger `copilot: user accepted a photo edit`. Rejecting writes none.
- Not built: deleting a photo.
