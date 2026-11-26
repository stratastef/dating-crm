# Photos

Routes are in `app/photos.py`; the table is `photos` (one row per photo). A photo is `{"id", "rank", "reason", "suggested_edit", "edit"}`.

| Route | Does |
| --- | --- |
| `POST /photos` | Store one photo. The body is the file itself, with `Content-Type: image/jpeg` or `image/png`. |
| `GET /photos` | List the photos in `rank` order, the lead photo first. Photos added since the last rank or order come last. |
| `POST /photos/rank` | Have Claude look at all the photos and store a `rank` (1 is best) and a `reason` for each. It may also offer a light edit per photo, stored as `suggested_edit`. |
| `PUT /photos/order` with `{"ids": [3, 1, 2]}` | Set the order: each photo's `rank` becomes its place, 1 the lead photo. Returns the photos in that order. `422` unless `ids` names each of the user's photos exactly once. |
| `DELETE /photos/{id}` | Delete the photo and its file (`204`). It cannot be undone. |
| `GET /photos/{id}/preview` | The photo with the edit on offer applied. Stores nothing. |
| `PUT /photos/{id}/edit` with `{"accept": true}` | Accept or reject the edit on offer. An accepted edit becomes `edit`; either way `suggested_edit` is cleared. |
| `GET /photos/{id}/image` | The photo with the accepted edit applied, or the file as uploaded. |

- **Files** are on local disk under `PHOTOS_DIR` (default `./photos`), as `<user id>/<photo id>`. Compose sets it to `/data/photos` on the `photos` volume, shared by the API and worker. Back that volume up with the database. The uploaded file is never changed; it is deleted with its photo.
- **Upload limits:** at most 10 MB (`413`), `image/jpeg` or `image/png` only (`415`), and the file must really be that type (`422`).
- **Edits are not generated.** An edit is `{"crop": [left, top, right, bottom] or null, "exposure", "colour"}`: crop in fractions of the width and height, the two factors from 0.5 to 1.5 where 1 changes nothing. Claude only proposes these numbers. `_edited()` applies them to the uploaded file with Pillow. No route returns pixels from a model.
- Claude is called with the photos through `llm.call(..., images=[(content_type, data)])`. Each photo is sent scaled down to 1024 pixels a side.
- The rank route returns `409` when the user has no photos, and `502` when Claude's reply does not rank exactly the user's photos or holds an edit outside the limits; nothing is stored then.
- Nothing is uploaded to a dating app and nothing rotates photos: the user saves the photo they want and changes their profile themselves.
- Accepting an edit writes an audit log entry: type `profile_change`, app `all` (a photo belongs to no one dating app), target `photo:<photos.id>`, trigger `copilot: user accepted a photo edit`. Rejecting writes none.
- **Order.** `rank` is the photo's place on the profile, set by the latest of `POST /photos/rank` (Claude's order) and `PUT /photos/order` (the user's). Ordering keeps each `reason`, which says why Claude ranked the photo where it did. The phone labels the first photo "Lead photo".
- Deleting or ordering a photo writes no audit log entry: neither changes a dating app.

## On the phone

**`PhotosView`**: the photos in the server's order; the first is labeled "Lead photo", the others show Claude's reason. Edit (or a drag) reorders them and sends the whole order (`PUT /photos/order`); a failed save puts the old order back. Swipe or Edit deletes one after a confirmation (`DELETE /photos/{id}`). An edit on offer shows under AI suggests, the original and the edited preview side by side at every text size, then Accept edit and Keep original.

- Not verified on screen: reorder, delete, Accept edit and Keep original on Photos; Rewrite, Accept and the Voice link on Bios. The rewrite needs Claude and a tap, so it was never shown.
