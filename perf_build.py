import timeit

setup = """
from core.executor.command_builder import CommandBuilder
from pathlib import Path

def make_builder():
    builder = CommandBuilder()
    builder.input("input.mp4")
    builder.output("output.mp4")
    builder.scale(1280, 720)
    builder.fps(30)
    builder.eq(brightness=0.1, contrast=1.1)
    return builder
"""

stmt = "make_builder().build_args()"

print(timeit.timeit(stmt, setup=setup, number=10000))
