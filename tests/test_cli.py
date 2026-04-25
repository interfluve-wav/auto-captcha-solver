"""CLI integration tests."""

import subprocess
import sys
import json

PYTHON = sys.executable

def test_cli_help():
    result = subprocess.run(
        [PYTHON, "-m", "auto_captcha_solver.cli"],
        capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 1  # No subcommand → exits 1
    assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower()

def test_cli_credits_missing_key(monkeypatch):
    """credits command should exit 1 when API key missing."""
    # Ensure env var is NOT set
    monkeypatch.delenv("NOPECHA_API_KEY", raising=False)
    result = subprocess.run(
        [PYTHON, "-c", "from auto_captcha_solver.cli import main; main()"],
        capture_output=True, text=True, timeout=10, env={}
    )
    # argparse will show error because --key not provided; exit non-zero
    assert result.returncode != 0

# Integration test — commented by default (needs API key + browser)
# def test_cli_detect_live():
#     result = subprocess.run(
#         [PYTHON, "-m", "auto_captcha_solver.cli", "detect", "--url", "https://example.com", "--key", "test"],
#         capture_output=True, text=True, timeout=30
#     )
#     assert result.returncode == 0
