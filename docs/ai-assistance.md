# AI-assistance disclosure

ChangeSafe was developed with AI-assisted planning and implementation support.

AI assistance was used to:

- Analyze and turn the design specification into an implementation plan.
- Draft application code, tests, documentation, and responsive visual concepts.
- Investigate test and container failures and propose bounded fixes.
- Generate candidate copy for the demo and submission material.

Controls applied during development:

- Changes were made in an isolated Git worktree and reviewed through diffs and automated checks.
- Features and fixes followed red-then-green tests where practical.
- Browser behavior was exercised against the running local application at desktop and phone widths.
- Completion claims are based on fresh test, build, container, and HTTP evidence.
- Credentials remain in an external private environment file; secret values were not read into prompts, source, screenshots, or fixtures.
- Generated migration code is never trusted merely because an AI produced it. Deterministic templates, allowlists, parsers, hashes, and human approval remain authoritative.

The optional OpenAI capability inside ChangeSafe is similarly bounded: it supplies strict planning/narrative fields only. It cannot set risk, choose arbitrary output paths, execute code, approve publication, or mutate external systems.

The project owner remains responsible for reviewing the code, integration scopes, live evidence, deployment configuration, and any external publication.
