import timeit

setup = """
def sanitize_text_param_opt(text: str) -> str:
    if not text:
        return text

    if "\0" in text:
        raise ValueError("Null byte found in text parameter")

    # Fast path: if none of the special chars are in the string, return immediately
    # The set of chars we replace: \\, ', :, ;, %, ,, [, ]
    if not any(c in text for c in "\\':;%,[]"):
        return text

    if "\\" in text:
        text = text.replace("\\", "\\\\")
    if "'" in text:
        text = text.replace("'", "\\'")
    if ":" in text:
        text = text.replace(":", "\\:")
    if ";" in text:
        text = text.replace(";", "\\;")
    if "%" in text:
        text = text.replace("%", "%%")
    if "," in text:
        text = text.replace(",", "\\,")
    if "[" in text:
        text = text.replace("[", "\\[")
    if "]" in text:
        text = text.replace("]", "\\]")

    return text
"""

stmt_clean = "sanitize_text_param_opt(\"clean_string_without_symbols\")"
stmt_dirty = "sanitize_text_param_opt(\"dirty:string,with=symbols\")"

print("Clean string:", timeit.timeit(stmt_clean, setup=setup, number=100000))
print("Dirty string:", timeit.timeit(stmt_dirty, setup=setup, number=100000))
