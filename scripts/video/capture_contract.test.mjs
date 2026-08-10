import assert from "node:assert/strict";
import test from "node:test";

import {
  SCENE_IDS,
  assertSafeBaseUrl,
  overlayModel,
  sceneDeadline,
  validateTimingManifest,
} from "./capture_contract.mjs";

function validManifest() {
  return {
    version: 1,
    total_duration_ms: 170_000,
    scenes: SCENE_IDS.map((scene_id, index) => ({
      scene_id,
      start_ms: index * 20_000,
      duration_ms: 10_000,
      audio_path: `audio/${scene_id}.mp3`,
    })),
    captions: [
      {
        cue_id: "problem-1",
        scene_id: "problem",
        start_ms: 0,
        end_ms: 2_000,
        text: "A column rename looks simple.",
      },
    ],
  };
}

test("accepts only the permanent HTTPS application origin", () => {
  assert.equal(
    assertSafeBaseUrl("https://changesafe-competition.onrender.com"),
    "https://changesafe-competition.onrender.com",
  );
  for (const value of [
    "http://changesafe-competition.onrender.com",
    "https://example.invalid",
    "https://user:pass@changesafe-competition.onrender.com",
  ]) {
    assert.throws(() => assertSafeBaseUrl(value), /approved hosted origin/);
  }
});

test("rejects timing manifests that reorder or exceed scenes", () => {
  const reordered = validManifest();
  reordered.scenes.reverse();
  assert.throws(
    () => validateTimingManifest(reordered, "C:/video-work"),
    /scene order/,
  );
  const overlong = validManifest();
  overlong.total_duration_ms = 175_001;
  assert.throws(
    () => validateTimingManifest(overlong, "C:/video-work"),
    /175000/,
  );
});

test("rejects unsafe media paths and malformed caption timelines", () => {
  const unsafe = validManifest();
  unsafe.scenes[0].audio_path = "../secret.mp3";
  assert.throws(
    () => validateTimingManifest(unsafe, "C:/video-work"),
    /video work directory/,
  );
  const duplicate = validManifest();
  duplicate.captions.push({ ...duplicate.captions[0] });
  assert.throws(
    () => validateTimingManifest(duplicate, "C:/video-work"),
    /cue IDs/,
  );
});

test("overlay text is data and never an HTML field", () => {
  const model = overlayModel("<img src=x onerror=alert(1)>", "55 fields");
  assert.equal(model.caption, "<img src=x onerror=alert(1)>");
  assert.equal(model.callout, "55 fields");
  assert.equal(Object.hasOwn(model, "html"), false);
});

test("scene deadline is derived from persisted timing", () => {
  assert.equal(sceneDeadline({ start_ms: 12_000, duration_ms: 8_000 }), 20_000);
});
