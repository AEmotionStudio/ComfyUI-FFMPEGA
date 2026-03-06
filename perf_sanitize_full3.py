import timeit

setup = """
def sanitize_text_param_orig(text: str) -> str:
    if not text:
        return text

    if "\\0" in text:
        pass

    if "\\\\" in text:
        text = text.replace("\\\\", "\\\\\\\\")
    if "'" in text:
        text = text.replace("'", "\\\\'")
    if ":" in text:
        text = text.replace(":", "\\\\:")
    if ";" in text:
        text = text.replace(";", "\\\\;")
    if "%" in text:
        text = text.replace("%", "%%")
    if "," in text:
        text = text.replace(",", "\\\\,")
    if "[" in text:
        text = text.replace("[", "\\\\[")
    if "]" in text:
        text = text.replace("]", "\\\\]")

    return text

def sanitize_text_param_set(text: str) -> str:
    if not text:
        return text

    if "\\0" in text:
        pass

    if not set(text).intersection("\\\\':;%,[]"):
        return text

    if "\\\\" in text:
        text = text.replace("\\\\", "\\\\\\\\")
    if "'" in text:
        text = text.replace("'", "\\\\'")
    if ":" in text:
        text = text.replace(":", "\\\\:")
    if ";" in text:
        text = text.replace(";", "\\\\;")
    if "%" in text:
        text = text.replace("%", "%%")
    if "," in text:
        text = text.replace(",", "\\\\,")
    if "[" in text:
        text = text.replace("[", "\\\\[")
    if "]" in text:
        text = text.replace("]", "\\\\]")

    return text
"""

stmt_clean_orig = "sanitize_text_param_orig(\"clean_string_without_symbols\")"
stmt_dirty_orig = "sanitize_text_param_orig(\"dirty:string,with=symbols\")"

stmt_clean_set = "sanitize_text_param_set(\"clean_string_without_symbols\")"
stmt_dirty_set = "sanitize_text_param_set(\"dirty:string,with=symbols\")"

print("ORIG Clean string:", timeit.timeit(stmt_clean_orig, setup=setup, number=1000000))
print("ORIG Dirty string:", timeit.timeit(stmt_dirty_orig, setup=setup, number=1000000))
print("SET Clean string:", timeit.timeit(stmt_clean_set, setup=setup, number=1000000))
print("SET Dirty string:", timeit.timeit(stmt_dirty_set, setup=setup, number=1000000))
