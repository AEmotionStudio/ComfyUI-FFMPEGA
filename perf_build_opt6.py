import timeit

setup = """
from dataclasses import dataclass, field
from typing import Optional

try:
    from core.sanitize import sanitize_text_param
except ImportError:
    def sanitize_text_param(text: str) -> str:
        if not text:
            return text
        if "\\0" in text:
            pass
        if not any(c in text for c in "\\\\':;%,[]"):
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
                    val_str = str(v)
                    if isinstance(v, str):
                        val_str = sanitize_text_param(val_str)
                    kv_pairs.append(f"{k}={val_str}")
            param_str = ":".join(kv_pairs)
            parts.append(f"{self.name}={param_str}")
        else:
            parts.append(self.name)

        for out in self.outputs:
            parts.append(f"[{out}]")
        return "".join(parts)

    def to_string_opt(self) -> str:
        s = ""
        for inp in self.inputs:
            s += f"[{inp}]"

        if self.params:
            s += self.name + "="
            first = True
            for k, v in self.params.items():
                if not first:
                    s += ":"
                if v is None:
                    s += k
                elif type(v) is str:
                    s += f"{k}={sanitize_text_param(v)}"
                else:
                    s += f"{k}={v}"
                first = False
        else:
            s += self.name

        for out in self.outputs:
            s += f"[{out}]"

        return s

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
        return ",".join(f.to_string_opt() for f in self.filters)

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
