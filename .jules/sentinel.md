## 2025-02-09 - FFMPEG Parameter Injection
**Vulnerability:** FFMPEG filter parameters were constructed using unsanitized string interpolation, allowing injection of arbitrary filter options (like `textfile='/etc/passwd'` in `drawtext`) or chaining new filters via `,`.
**Learning:** Even when wrapping parameters in quotes (e.g. `font='{font}'`), injection is possible if the value can escape the quotes (`'`) or inject delimiters (`:` or `,`). `shlex.quote` protects shell arguments but not the internal FFMPEG filter syntax.
**Prevention:** Sanitize ALL user-provided strings used in FFMPEG filter graphs. Escape `:`, `,`, `'`, `\`, and potentially `%`.
