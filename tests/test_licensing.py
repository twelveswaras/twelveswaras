"""The repo's licence statements match what it ships.

    python tests/test_licensing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Datasets whose terms allow the result to ship in an MIT/CC-BY repo. Saraga is CC-BY-NC-SA.
CC_BY = {"compmusic_raga"}


def test_reference_profiles_are_built_only_from_cc_by_data():
    from tools import build_raaga_profiles as b

    assert set(b.DATASETS) <= CC_BY


def test_readme_states_the_recognizer_is_agpl_and_the_model_cc_by():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lic = text[text.index("## Licensing"):]
    lic = lic.split("\n## ")[0]                 # up to the next section, if any
    assert "AGPL-3.0" in lic and "Essentia" in lic
    assert "CC-BY-4.0" in lic and "non-commercial use" not in lic


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
