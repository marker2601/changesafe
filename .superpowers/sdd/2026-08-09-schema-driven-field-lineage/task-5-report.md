# Task 5 Report: schema-backed current-field selection

## Status

Completed and ready for independent review. The change request now reads its
current field from the active DataHub schema catalog or an explicitly selected,
checksum-verified recorded catalog. A user cannot submit a free-text field or
carry a previous field's type/destination into a different field request.

## RED evidence

- New hook and combobox tests initially failed because
  `useSchemaCatalog` and `FieldCombobox` did not exist.
- Form and draft tests then failed as expected: `Current field` was a plain
  textbox, `Current type` was editable, invalid fields still enabled Analyze,
  discovery errors had no safe recovery UI, and `isOfficialDataset` was absent.
- App tests failed as expected before wiring with `schema` undefined, proving
  the existing app had no schema-backed field selection path.
- A late-response test exposed a real source-switch race during implementation:
  a changed Dataset URN briefly issued a recorded request. The hook now derives
  an active source for a new URN before any request starts; its regression test
  is included.

## Implementation

- Added `useSchemaCatalog` with session-local successful-response cache,
  request-id and cleanup stale-response protection, retry, invalid-URN safe
  no-op behavior, and explicit recorded-source loading.
- Added an accessible searchable combobox: returned fields only, keyboard
  navigation, Escape restoration, selected/active ARIA state, type, and
  nullability detail.
- `App` owns schema selection. Changing fields binds the returned native type,
  clears incompatible destination/type values, and does not mutate a submitted
  run request or analysis.
- `ChangeForm` blocks Analyze until an exact returned field and operation inputs
  are valid. It shows schema provenance, loading, safe error/retry state, and
  an explicit `Use recorded fields` action only for AUTO mode.
- Replaced the narrow fixture with the complete 55-field `order_details`
  catalog; no recorded evidence or dependency semantics were changed.
- Added compact token-based dropdown/error styling with scroll bounds and
  narrow-screen wrapping.

## GREEN evidence

- Focused Vitest: `44 passed` across schema hook, combobox, form, draft, and
  App tests.
- Full web Vitest: `95 passed` in `17` files.
- `pnpm --filter @changesafe/web typecheck`: passed.
- `pnpm --filter @changesafe/web lint`: passed with zero warnings.
- `pnpm --filter @changesafe/web build`: passed.
- `git diff --check`: passed.

## Self-review

- The combobox never promotes typed text to a valid field; only a supplied
  `SchemaField` can update the draft.
- Current type is read-only schema evidence for type changes.
- The hook never lets a prior request replace catalog data for a newer URN and
  resets an asset change to `active` before issuing a read.
- Browser code uses only the typed API catalog and contains no credential or
  token handling.
- Submitted requests remain the displayed source of truth while their run is
  shown; draft state is not used to rewrite past analysis.

## Concerns

- The session-local cache is intentionally in-memory only. Reloading the page
  fetches fresh schema evidence, while a component reset within a session can
  reuse a successful response.
- Rendered 430px and browser-flow QA are deliberately left to the controller's
  post-review visual pass, as requested; this task did not use Playwright or a
  browser.
