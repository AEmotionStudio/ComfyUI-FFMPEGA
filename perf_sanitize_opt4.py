import timeit

setup = """
def sanitize_text_param_orig(text: str) -> str:
    if not text:
        return text

    if '\\0' in text:
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

TRANS = str.maketrans({
    "\\\\": "\\\\\\\\",
    "'": "\\\\'",
    ":": "\\\\:",
    ";": "\\\\;",
    "%": "%%",
    ",": "\\\\,",
    "[": "\\\\[",
    "]": "\\\\]"
})

def sanitize_text_param_opt(text: str) -> str:
    if not text:
        return text

    if '\\0' in text:
        pass

    return text.translate(TRANS)
"""

stmt_clean_orig = "sanitize_text_param_orig(\"clean_string_without_symbols\")"
stmt_dirty_orig = "sanitize_text_param_orig(\"dirty:string,with=symbols\")"

stmt_clean_opt = "sanitize_text_param_opt(\"clean_string_without_symbols\")"
stmt_dirty_opt = "sanitize_text_param_opt(\"dirty:string,with=symbols\")"


print("ORIG Clean string:", timeit.timeit(stmt_clean_orig, setup=setup, number=100000))
print("ORIG Dirty string:", timeit.timeit(stmt_dirty_orig, setup=setup, number=100000))
print("OPT Clean string:", timeit.timeit(stmt_clean_opt, setup=setup, number=100000))
print("OPT Dirty string:", timeit.timeit(stmt_dirty_opt, setup=setup, number=100000))
