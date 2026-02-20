## 2025-02-09 - FFMPEG Parameter Injection
**Vulnerability:** FFMPEG filter parameters were constructed using unsanitized string interpolation, allowing injection of arbitrary filter options (like `textfile='/etc/passwd'` in `drawtext`) or chaining new filters via `,`.
**Learning:** Even when wrapping parameters in quotes (e.g. `font='{font}'`), injection is possible if the value can escape the quotes (`'`) or inject delimiters (`:` or `,`). `shlex.quote` protects shell arguments but not the internal FFMPEG filter syntax.
**Prevention:** Sanitize ALL user-provided strings used in FFMPEG filter graphs. Escape `:`, `,`, `'`, `\`, and potentially `%`.

## 2025-02-13 - Command Injection via Choice Parameters
**Vulnerability:** A critical command injection vulnerability was found in FFMPEG command construction. The `SkillComposer` validated parameters but only logged warnings on failure, allowing malicious payloads (e.g., breaking out of filter syntax) to pass through to `_f_skill` handlers which used them unsafely.
**Learning:** Validation functions that return status (boolean/errors) must be strictly enforced. "Soft" validation that only warns is dangerous for security-critical operations like shell command construction.
**Prevention:** Enforce "fail-closed" validation. If a parameter is invalid, discard it or fail the operation. Never assume inputs are safe just because a validation function was called; check its result.

## 2025-02-14 - FFMPEG Coordinate Parameter Injection
**Vulnerability:** User-controlled coordinate parameters (like `x` and `y` in `drawtext`, `crop`, `pad`) were not sanitized, allowing attackers to inject arbitrary FFMPEG filter options by using the `:` delimiter (e.g., `x="0:fontfile='/etc/passwd'"`).
**Learning:** Parameters expected to be mathematical expressions (like `(w-text_w)/2`) are still strings and can contain malicious delimiters. Simply casting to string is insufficient.
**Prevention:** Apply `sanitize_text_param` to ALL user-supplied filter parameters. This function correctly escapes `:` and `,`, preventing argument injection while preserving valid expression syntax (assuming commas in expressions are also escaped, which FFMPEG requires).

## 2026-02-16 - API Key Leakage via Streaming Error Paths
**Vulnerability:** `APIConnector.generate_stream()` in `core/llm/api.py` did not sanitize API keys from HTTP error messages, unlike sibling methods `generate()` and `chat_with_tools()`. A failed streaming request could expose API keys via request headers in error messages.
**Learning:** When adding new methods that make HTTP calls with auth headers, it's easy to forget the error-sanitization wrapper since the happy path works fine. The inconsistency arose because `generate_stream` had no try/except wrapper at all.
**Prevention:** Whenever adding new HTTP-calling methods to API connectors, always include the try/except sanitization wrapper. Consider extracting the error-handling pattern into a shared utility.

## 2025-05-23 - Prevent Arbitrary File Writes to System Directories
**Vulnerability:** The `validate_output_path` function prevented directory traversal via `..` but allowed absolute paths to any location (e.g., `/usr/bin/malicious_file`). This could allow an attacker to overwrite critical system files if the process had sufficient permissions.
**Learning:** Checking for `..` in path components is insufficient for preventing arbitrary file writes when absolute paths are allowed. Validation must also check if the resolved path targets sensitive system directories.
**Prevention:** Implemented a blocklist of critical system directories (e.g., `/bin`, `/etc`, `/usr`) in `core/sanitize.py` and enforced this check in both `validate_output_path` and `validate_output_file_path`. Ideally, an allowlist of safe directories (sandbox) should be used, but a blocklist provides immediate defense-in-depth without breaking flexible workflows.
