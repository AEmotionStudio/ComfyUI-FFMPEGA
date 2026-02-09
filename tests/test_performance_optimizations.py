
import pytest
import os
import importlib

# Dynamic import to support relative imports within the package
root_name = os.path.basename(os.getcwd())
try:
    m = importlib.import_module(f"{root_name}.skills.composer")
    SkillComposer = m.SkillComposer
    Pipeline = m.Pipeline
except ImportError:
    from skills.composer import SkillComposer, Pipeline

def test_verify_optimization(capsys):
    composer = SkillComposer()

    # Test 1: Trim (Input seeking optimization)
    pipeline_trim = Pipeline(
        input_path="input.mp4",
        output_path="output.mp4"
    ).add_step("trim", {"start": 10, "end": 20})

    cmd_trim_str = composer.compose(pipeline_trim).to_string()
    print(f"\nTRIM COMMAND: {cmd_trim_str}")

    # Verify -ss is used (seeking)
    assert "-ss 10" in cmd_trim_str
    # Verify duration is calculated correctly (20 - 10 = 10)
    assert "-t 10.0" in cmd_trim_str
    # Verify input seeking: -ss comes before -i
    assert cmd_trim_str.index("-ss") < cmd_trim_str.index("-i")

    # Test 2: HW Accel (Placement correction)
    pipeline_hw = Pipeline(
        input_path="input.mp4",
        output_path="output.mp4"
    ).add_step("hwaccel", {"type": "cuda"})

    cmd_hw_str = composer.compose(pipeline_hw).to_string()
    print(f"HWACCEL COMMAND: {cmd_hw_str}")

    # Verify -hwaccel is present
    assert "-hwaccel cuda" in cmd_hw_str
    # Verify placement: -hwaccel comes before -i (input option)
    assert cmd_hw_str.index("-hwaccel") < cmd_hw_str.index("-i")
