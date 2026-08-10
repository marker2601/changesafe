import path from "node:path";

export const SCENE_IDS = [
  "problem",
  "truth-boundary",
  "schema-request",
  "lineage",
  "impact",
  "artifacts",
  "multi-field",
  "approval",
  "closing",
];

const APPROVED_ORIGIN = "https://changesafe-competition.onrender.com";

export function assertSafeBaseUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("Base URL must use the approved hosted origin.");
  }
  if (
    parsed.origin !== APPROVED_ORIGIN ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    (parsed.pathname !== "/" && parsed.pathname !== "") ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error("Base URL must use the approved hosted origin.");
  }
  return parsed.origin;
}

function assertInside(root, candidate) {
  if (typeof candidate !== "string" || candidate.length === 0) {
    throw new Error("Scene audio path is required.");
  }
  const resolved = path.resolve(root, candidate);
  const relative = path.relative(root, resolved);
  if (path.isAbsolute(candidate) || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Scene audio must remain inside the video work directory.");
  }
}

export function validateTimingManifest(value, workDir) {
  if (value?.version !== 1 || !Array.isArray(value.scenes)) {
    throw new Error("Timing manifest version 1 is required.");
  }
  const ids = value.scenes.map((scene) => scene.scene_id);
  if (JSON.stringify(ids) !== JSON.stringify(SCENE_IDS)) {
    throw new Error("Timing manifest scene order is invalid.");
  }
  if (
    !Number.isInteger(value.total_duration_ms) ||
    value.total_duration_ms <= 0 ||
    value.total_duration_ms > 175_000
  ) {
    throw new Error("Timing manifest must not exceed 175000 ms.");
  }
  const root = path.resolve(workDir);
  let previousEnd = 0;
  for (const scene of value.scenes) {
    if (
      !Number.isInteger(scene.start_ms) ||
      !Number.isInteger(scene.duration_ms) ||
      scene.start_ms < previousEnd ||
      scene.duration_ms <= 0
    ) {
      throw new Error("Timing manifest scene timeline is invalid.");
    }
    previousEnd = sceneDeadline(scene);
    assertInside(root, scene.audio_path);
  }
  if (previousEnd !== value.total_duration_ms) {
    throw new Error("Timing manifest total does not match its scenes.");
  }

  if (!Array.isArray(value.captions)) {
    throw new Error("Timing manifest captions are required.");
  }
  const cueIds = new Set();
  let previousCueStart = -1;
  for (const cue of value.captions) {
    if (cueIds.has(cue.cue_id)) {
      throw new Error("Timing manifest cue IDs must be unique.");
    }
    cueIds.add(cue.cue_id);
    if (
      !SCENE_IDS.includes(cue.scene_id) ||
      !Number.isInteger(cue.start_ms) ||
      !Number.isInteger(cue.end_ms) ||
      cue.start_ms < previousCueStart ||
      cue.start_ms < 0 ||
      cue.end_ms <= cue.start_ms ||
      cue.end_ms > value.total_duration_ms
    ) {
      throw new Error("Timing manifest caption timeline is invalid.");
    }
    if (typeof cue.text !== "string" || cue.text.length > 96) {
      throw new Error("Timing manifest captions must not exceed 96 characters.");
    }
    previousCueStart = cue.start_ms;
  }
  return value;
}

export function overlayModel(caption, callout = "") {
  return { caption: String(caption), callout: String(callout) };
}

export function sceneDeadline(scene) {
  return scene.start_ms + scene.duration_ms;
}
