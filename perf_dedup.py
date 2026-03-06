import timeit

setup = """
def dedup_output_options_orig(output_options):
    seen_flags = {}
    deduped = []
    i = 0
    while i < len(output_options):
        opt = output_options[i]
        if (
            opt.startswith("-")
            and i + 1 < len(output_options)
            and not output_options[i + 1].startswith("-")
        ):
            flag, val = opt, output_options[i + 1]
            if flag == "-map" or flag not in seen_flags:
                seen_flags[flag] = len(deduped)
                deduped.extend([flag, val])
            else:
                idx = seen_flags[flag]
                deduped[idx + 1] = val
            i += 2
        else:
            if opt not in seen_flags:
                seen_flags[opt] = len(deduped)
                deduped.append(opt)
            i += 1
    return deduped
"""

stmt_clean_orig = "dedup_output_options_orig(['-c:v', 'libx264', '-crf', '23', '-preset', 'medium', '-c:a', 'aac', '-b:a', '128k', '-map', '0:v', '-map', '1:a', '-c:v', 'copy'])"

print("ORIG Clean string:", timeit.timeit(stmt_clean_orig, setup=setup, number=100000))
