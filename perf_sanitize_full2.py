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

import re
ESCAPE_RE = re.compile(r"([\\\\':;%,\\[\\]])")

def sanitize_text_param_re(text: str) -> str:
    if not text:
        return text

    if "\\0" in text:
        pass

    if not ESCAPE_RE.search(text):
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

stmt_clean_re = "sanitize_text_param_re(\"clean_string_without_symbols\")"
stmt_dirty_re = "sanitize_text_param_re(\"dirty:string,with=symbols\")"


print("ORIG Clean string:", timeit.timeit(stmt_clean_orig, setup=setup, number=1000000))
print("ORIG Dirty string:", timeit.timeit(stmt_dirty_orig, setup=setup, number=1000000))
print("RE Clean string:", timeit.timeit(stmt_clean_re, setup=setup, number=1000000))
print("RE Dirty string:", timeit.timeit(stmt_dirty_re, setup=setup, number=1000000))
