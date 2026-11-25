# Find and purge

A match can ask for their data to be deleted. Routes are in `app/purge.py`.

| Route | Does |
| --- | --- |
| `GET /people?q=` | The caller's cards, on every app, whose name or handle (`external_id`) contains `q`, ignoring case. |
| `GET /people/candidates?q=` | The caller's swipe candidates, on every app, whose name or profile ID contains `q`, ignoring case. A person the user only swiped on is a candidate, not a card. |
| `POST /people/purge` | Delete the cards in `card_ids` and the swipe candidates in `candidate_ids`, and everything stored about them. Body: `{"card_ids": [1, 2], "candidate_ids": [7], "confirm": "purge"}`; at least one ID. Returns `{"purged": 3}`. A purged candidate's audit entries (target `candidate:<id>`) are deleted by the `swipe_candidates_purge_audit_log` trigger, and one `purge` entry is added. |

- The purge cannot be undone. Without `"confirm": "purge"` the request is `422`. It runs in one transaction: if any card is not the caller's it is `404` and nothing is deleted.
- Every table that holds data about a match must reference `cards` (directly or through another table) with `ON DELETE CASCADE`; deleting the card is the purge. `tests/test_purge.py` reads the foreign keys from the database, so a new card table fails `test_no_row_for_a_purged_person_remains_in_any_table` until that test seeds a row in it. Anything kept outside Postgres needs its own delete in `purge_people()`: today that is the Google Calendar events of the card's holds, held or confirmed, whose titles carry the match's name. No file about a match is kept on disk: `card_photos` holds URLs, an imported screenshot is not stored, and the files under `PHOTOS_DIR` are the user's own photos.
- Audit log: the entries about the purged match are deleted, not kept or blanked, because `target` identifies the person. The `cards_purge_audit_log` trigger does it when the card is deleted, which is the only delete the append-only trigger lets through besides deleting the user. The purge then adds one entry per card: type `purge`, the card's app, target `card:<id>` (an id that now points at nothing), trigger `deletion request`.
- **A purged person stays purged.** The purge stores one tombstone per card with an `external_id` and per candidate, in `purge_tombstones`: a keyed hash (HMAC-SHA256 under `TOKEN_VAULT_MASTER_KEY`) of the user, the app and the app's ID for the person. It holds no name, app or ID. `app/tombstones.py` has `bury()` and `is_buried()`. Every path that stores a match or a candidate asks `is_buried()` first: `upsert_card()` returns `None` for a purged match (sync then skips their messages), `POST /cards` with their `external_id` is `409`, and `screen()` skips a purged profile. New code that stores a person from an app must ask too.
- Limits of the tombstone: a new master key forgets all of them. A card without an `external_id` has none, so a screenshot of the same chat makes a new card. A purged candidate who later becomes a match has another ID and gets a card.
- `connector_alerts` holds no match or profile ID (see "Connectors"), so a purge has nothing to delete there.
- Not covered: backups made before the purge still hold the data until they expire.
