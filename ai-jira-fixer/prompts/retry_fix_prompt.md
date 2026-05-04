The previous patch failed automated validation (lint / tests / build) in CI-like commands.

TASK
Apply exactly one conservative correction pass. Prefer the smallest possible edit.

RULES
- Do not expand scope beyond fixing the validation failures.
- Do not touch unrelated modules.

At the end, output on its own line:

CONFIDENCE: <integer 0-100>
