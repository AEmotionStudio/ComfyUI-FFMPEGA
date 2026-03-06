import timeit

setup = """
from core.executor.command_builder import CommandBuilder, FFMPEGCommand
from pathlib import Path

def make_builder():
    builder = CommandBuilder()
    builder.input("input.mp4")
    builder.output("output.mp4")
    builder.scale(1280, 720)
    builder.fps(30)
    builder.eq(brightness=0.1, contrast=1.1)
    return builder

def make_builder_opt():
    builder = CommandBuilderOpt()
    builder.input("input.mp4")
    builder.output("output.mp4")
    builder.scale(1280, 720)
    builder.fps(30)
    builder.eq(brightness=0.1, contrast=1.1)
    return builder

class FilterChainOpt:
    def __init__(self):
        self.filters = []

    def add(self, filter_obj):
        self.filters.append(filter_obj)
        return self

    def add_filter(self, name, params=None, inputs=None, outputs=None):
        self.filters.append((name, params or {}, inputs or [], outputs or []))
        return self

    def to_string(self) -> str:
        if not self.filters:
            return ""

        parts = []
        for name, params, inputs, outputs in self.filters:
            filter_parts = []
            for inp in inputs:
                filter_parts.append(f"[{inp}]")

            if params:
                kv_pairs = []
                for k, v in params.items():
                    if v is None:
                        kv_pairs.append(k)
                    else:
                        val_str = str(v)
                        # omit sanitize for test
                        kv_pairs.append(f"{k}={val_str}")
                param_str = ":".join(kv_pairs)
                filter_parts.append(f"{name}={param_str}")
            else:
                filter_parts.append(name)

            for out in outputs:
                filter_parts.append(f"[{out}]")

            parts.append("".join(filter_parts))

        return ",".join(parts)


class CommandBuilderOpt(CommandBuilder):
    def __init__(self):
        super().__init__()
        self._command.video_filters = FilterChainOpt()
        self._command.audio_filters = FilterChainOpt()
"""

stmt = "make_builder().build_args()"
stmt_opt = "make_builder_opt().build_args()"

print("ORIG:", timeit.timeit(stmt, setup=setup, number=10000))
print("OPT:", timeit.timeit(stmt_opt, setup=setup, number=10000))
