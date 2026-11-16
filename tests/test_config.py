import re
from pathlib import Path

from app.config import Settings

ENV_EXAMPLE = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")


def test_env_example_never_holds_a_real_key():
    """The template is shared. Real keys belong in .env, which is git-ignored."""
    keys = re.findall(r"^([A-Z_]*KEY)=(.*)$", ENV_EXAMPLE, re.M)
    assert keys
    for name, value in keys:
        assert not value.strip(), f"{name} must be empty in .env.example (put real keys in .env)"


def test_the_defaults_shown_in_env_example_match_config_py():
    """So changing a setting in one place can't quietly disagree with the other."""
    shown = dict(re.findall(r"^# ([A-Z_]+)=(.*)$", ENV_EXAMPLE, re.M))
    assert shown
    for name, value in shown.items():
        assert str(Settings.model_fields[name.lower()].default) == value, name
