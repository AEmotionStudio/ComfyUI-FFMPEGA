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

def dedup_output_options_opt(output_options):
    seen_flags = {}
    deduped = []

    iterator = iter(output_options)
    for opt in iterator:
        if opt.startswith("-"):
            try:
                # look ahead
                next_opt = next(iterator)
                if next_opt.startswith("-"):
                    # it was a flag without value, handle it
                    if opt not in seen_flags:
                        seen_flags[opt] = len(deduped)
                        deduped.append(opt)

                    # now handle next_opt (the next flag without value possibly)
                    # wait we can't do this easily.
                    pass
            except StopIteration:
                pass
"""
