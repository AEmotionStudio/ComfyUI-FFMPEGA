
import pytest
from skills.handlers.composite import _f_text_overlay

def test_security_injection_text_overlay():
    """Verify that 'enable' parameter injection is prevented."""

    # Payload with parameter injection attempt
    # Goal: Break out of enable='...' and inject textfile='/etc/passwd'
    payload = {
        "text": "Safe Text",
        "enable": "1':textfile='/etc/passwd"
    }

    # Call the handler
    vf, af, opts = _f_text_overlay(payload)

    assert len(vf) > 0
    cmd_str = vf[0]

    # Check that single quotes and colons are escaped
    # Expected: enable='1\'\:textfile=\'/etc/passwd'
    # If vulnerable: enable='1':textfile='/etc/passwd'

    # sanitize_text_param escapes ' to \' and : to \:
    assert "enable='1\\'\\:textfile=\\'/etc/passwd'" in cmd_str

    # Double check that we don't have unescaped injection
    assert ":textfile='/etc/passwd'" not in cmd_str
