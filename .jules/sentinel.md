## 2025-02-09 - FFMPEG Parameter Injection
**Vulnerability:** FFMPEG filter parameters were constructed using unsanitized string interpolation, allowing injection of arbitrary filter options (like `textfile='/etc/passwd'` in `drawtext`) or chaining new filters via `,`.
**Learning:** Even when wrapping parameters in quotes (e.g. `font='{font}'`), injection is possible if the value can escape the quotes (`'`) or inject delimiters (`:` or `,`). `shlex.quote` protects shell arguments but not the internal FFMPEG filter syntax.
**Prevention:** Sanitize ALL user-provided strings used in FFMPEG filter graphs. Escape `:`, `,`, `'`, `\`, and potentially `%`.

## 2025-02-13 - Command Injection via Choice Parameters
**Vulnerability:** A critical command injection vulnerability was found in FFMPEG command construction. The `SkillComposer` validated parameters but only logged warnings on failure, allowing malicious payloads (e.g., breaking out of filter syntax) to pass through to `_f_skill` handlers which used them unsafely.
**Learning:** Validation functions that return status (boolean/errors) must be strictly enforced. "Soft" validation that only warns is dangerous for security-critical operations like shell command construction.
**Prevention:** Enforce "fail-closed" validation. If a parameter is invalid, discard it or fail the operation. Never assume inputs are safe just because a validation function was called; check its result.
