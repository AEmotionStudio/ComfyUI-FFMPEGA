import timeit

setup = """
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Filter:
    name: str
    params: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)

    def to_string(self) -> str:
        parts = []
        for inp in self.inputs:
            parts.append(f"[{inp}]")
        if self.params:
            kv_pairs = []
            for k, v in self.params.items():
                if v is None:
                    kv_pairs.append(k)
                else:
                    kv_pairs.append(f"{k}={v}")
            parts.append(f"{self.name}={':'.join(kv_pairs)}")
        else:
            parts.append(self.name)
        for out in self.outputs:
            parts.append(f"[{out}]")
        return "".join(parts)

@dataclass
class FilterChain:
    filters: list = field(default_factory=list)
    def add(self, filter_obj):
        self.filters.append(filter_obj)
        return self
    def to_string(self) -> str:
        if not self.filters:
            return ""
        return ",".join(f.to_string() for f in self.filters)

@dataclass
class FilterChainOpt:
    filters: list = field(default_factory=list)
    def add(self, filter_obj):
        self.filters.append(filter_obj)
        return self
    def to_string(self) -> str:
        if not self.filters:
            return ""

        parts = []
        for f in self.filters:
            f_parts = []
            for inp in f.inputs:
                f_parts.append(f"[{inp}]")

            if f.params:
                kv_pairs = []
                for k, v in f.params.items():
                    if v is None:
                        kv_pairs.append(k)
                    else:
                        kv_pairs.append(f"{k}={v}")
                f_parts.append(f"{f.name}={':'.join(kv_pairs)}")
            else:
                f_parts.append(f.name)

            for out in f.outputs:
                f_parts.append(f"[{out}]")

            parts.append("".join(f_parts))

        return ",".join(parts)


filters_data = [
    Filter("scale", {"w": 1280, "h": 720}),
    Filter("fps", {"": 30}),
    Filter("eq", {"brightness": 0.1, "contrast": 1.1})
]

fc_orig = FilterChain(filters=filters_data)
fc_opt = FilterChainOpt(filters=filters_data)
"""

print("ORIG:", timeit.timeit("fc_orig.to_string()", setup=setup, number=100000))
print("OPT:", timeit.timeit("fc_opt.to_string()", setup=setup, number=100000))
