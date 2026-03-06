import timeit

setup = """
from dataclasses import dataclass, field

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
                        val_str = sanitize_text_param_orig(val_str)
                    kv_pairs.append(f"{k}={val_str}")
            param_str = ":".join(kv_pairs)
            parts.append(f"{self.name}={param_str}")
        else:
            parts.append(self.name)

        for out in self.outputs:
            parts.append(f"[{out}]")
        return "".join(parts)

    def to_string_opt(self) -> str:
        parts = []
        if self.inputs:
            parts.extend(f"[{inp}]" for inp in self.inputs)

        if self.params:
            kv_pairs = []
            for k, v in self.params.items():
                if v is None:
                    kv_pairs.append(k)
                elif type(v) is str:
                    kv_pairs.append(f"{k}={sanitize_text_param_orig(v)}")
                else:
                    kv_pairs.append(f"{k}={v}")
            parts.append(f"{self.name}={':'.join(kv_pairs)}")
        else:
            parts.append(self.name)

        if self.outputs:
            parts.extend(f"[{out}]" for out in self.outputs)

        return "".join(parts)

@dataclass
class FilterChain:
    filters: list = field(default_factory=list)
    def to_string(self) -> str:
        if not self.filters:
            return ""
        return ",".join(f.to_string() for f in self.filters)

@dataclass
class FilterChainOpt:
    filters: list = field(default_factory=list)
    def to_string(self) -> str:
        if not self.filters:
            return ""
        return ",".join(f.to_string_opt() for f in self.filters)

data = [Filter('scale', {'w': 1280, 'h': 720}, ['0:v'], ['out'])] * 10
fc = FilterChain(data)
fc_opt = FilterChainOpt(data)
"""

print("ORIG:", timeit.timeit("fc.to_string()", setup=setup, number=100000))
print("OPT:", timeit.timeit("fc_opt.to_string()", setup=setup, number=100000))
