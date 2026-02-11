
from skills.registry import get_registry
from skills.composer import SkillComposer, Pipeline

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
