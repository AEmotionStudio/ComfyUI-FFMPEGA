
from skills.registry import get_registry
from skills.composer import SkillComposer, Pipeline
import pytest
from skills.handlers.composite import _f_text_overlay, _f_ticker, _f_countdown, _f_typewriter_text
from skills.handlers.spatial import _f_crop, _f_pad, _f_resize

def test_vulnerability():
    registry = get_registry()
    composer = SkillComposer(registry)

    # Malicious payload injecting a drawtext filter
    # We use 'reds' to satisfy the start of selectivecolor, then break out with comma
    payload = "reds:cyan=0,drawtext=text='VULNERABLE':fontsize=100:fontcolor=red:x=100:y=100,selectivecolor=reds"

    pipeline = Pipeline(
        input_path="input.mp4",
        output_path="output.mp4"
    )

    # Add step with malicious parameter
    pipeline.add_step("selective_color", {
        "color_range": payload,
        "cyan": 0.0
    })

    command = composer.compose(pipeline)
    cmd_str = command.to_string()
    print("\nCommand constructed:", cmd_str)

    # Check if the injected filter is present
    if "drawtext=text='VULNERABLE'" in cmd_str or "VULNERABLE" in cmd_str:
        # Note: Depending on quoting, it might appear differently, but VULNERABLE should not be there if dropped.
        print("\n[!] VULNERABILITY CONFIRMED: Injected filter found in command.")
        assert False, "Command injection succeeded! Vulnerable payload present."
    else:
        print("\n[+] Payload seems to have been sanitized or rejected.")
        # Verify that selectivecolor is using the default 'reds'
        # The output format is selectivecolor=reds='...'
        # Or selectivecolor=reds:cyan=0.0...
        assert "selectivecolor=reds" in cmd_str

def assert_param_injection_prevented(func, params, param_name, malicious_val):
    p = params.copy()
    p[param_name] = malicious_val
    res = func(p)
    # res is (vf, af, opts) or (vf, af, opts, fc)
    filter_str = res[0][0] if res[0] else ""
    if not filter_str and len(res) > 3:
        filter_str = res[3]

    # Check if the injection is present unescaped
    # We look for e.g. ":fontfile=" which indicates a new parameter started
    # If sanitized, it should be "\:fontfile="

    injection_key = malicious_val.split(":", 1)[1].split("=")[0]
    vuln_pattern = f":{injection_key}="
    safe_pattern = f"\\:{injection_key}="

    if vuln_pattern in filter_str and safe_pattern not in filter_str:
        pytest.fail(f"Injection successful! Found unescaped '{vuln_pattern}' in '{filter_str}'")

def test_text_overlay_injection():
    # Inject fontfile parameter via x
    assert_param_injection_prevented(
        _f_text_overlay,
        {"text": "test"},
        "x",
        "0:fontfile='/etc/passwd'"
    )
    # Inject via y
    assert_param_injection_prevented(
        _f_text_overlay,
        {"text": "test"},
        "y",
        "0:fontfile='/etc/passwd'"
    )

def test_ticker_injection():
    # Inject via y
    assert_param_injection_prevented(
        _f_ticker,
        {"text": "test"},
        "y",
        "0:box=1"
    )

def test_countdown_injection():
    # Inject via x
    assert_param_injection_prevented(
        _f_countdown,
        {"start_from": 10},
        "x",
        "0:fontfile='/etc/passwd'"
    )

def test_typewriter_injection():
    # Inject via x
    assert_param_injection_prevented(
        _f_typewriter_text,
        {"text": "test"},
        "x",
        "0:fontfile='/etc/passwd'"
    )

def test_crop_injection():
    # Inject via x
    assert_param_injection_prevented(
        _f_crop,
        {"width": 100, "height": 100},
        "x",
        "0:exact=1"
    )
    # Inject via width
    assert_param_injection_prevented(
        _f_crop,
        {"x": 10, "y": 10},
        "width",
        "100:exact=1"
    )

def test_pad_injection():
    # Inject via x
    assert_param_injection_prevented(
        _f_pad,
        {"width": 100, "height": 100},
        "x",
        "0:color=red"
    )
    # Inject via width
    assert_param_injection_prevented(
        _f_pad,
        {"x": 10, "y": 10},
        "width",
        "100:color=red"
    )

def test_resize_injection():
    # Inject via width
    # resize returns [f"scale=..."], so we check the result
    assert_param_injection_prevented(
        _f_resize,
        {"height": 100},
        "width",
        "100:interl=1"
    )
