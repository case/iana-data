"""mise.toml pins tool versions; other files declare what those versions must be."""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MISE = REPO_ROOT / "mise.toml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

OPERATORS = (">=", "<=", "==", ">", "<")


def load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def parse_version(raw: str) -> tuple[int, ...]:
    """Parse a plain dotted version.

    Raises:
        ValueError: If any component is not a plain integer.
    """
    parts = raw.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"not a plain dotted version: {raw!r}")
    return tuple(int(part) for part in parts)


def satisfies(version: str, specifier: str) -> bool:
    """Check one PEP 440 specifier, refusing an operator this does not implement.

    Hand-rolled rather than importing `packaging`, which is present only as a
    transitive dependency. Deliberately narrow: an unknown operator raises.

    Raises:
        ValueError: If the specifier uses an operator outside OPERATORS.
    """
    specifier = specifier.strip()
    for operator in OPERATORS:
        if not specifier.startswith(operator):
            continue
        bound = parse_version(specifier.removeprefix(operator).strip())
        actual = parse_version(version)
        # Pad to equal length so 0.11 and 0.11.29 order the way a reader expects.
        width = max(len(bound), len(actual))
        bound += (0,) * (width - len(bound))
        actual += (0,) * (width - len(actual))
        return {
            ">=": actual >= bound,
            "<=": actual <= bound,
            "==": actual == bound,
            ">": actual > bound,
            "<": actual < bound,
        }[operator]
    raise ValueError(f"unrecognized version specifier: {specifier!r}")


def test_mise_pins_uv_within_the_version_pyproject_requires():
    """A mise-installed uv that pyproject rejects breaks bin/setup on a fresh clone."""
    pinned = load(MISE)["tools"]["uv"]
    required = load(PYPROJECT)["tool"]["uv"]["required-version"]

    for clause in required.split(","):
        assert satisfies(pinned, clause), (
            f"mise.toml pins uv {pinned}, outside pyproject's required-version "
            f"{required!r}. Bump one to match the other."
        )


def test_every_mise_tool_is_pinned_to_an_exact_version():
    """A floating pin makes the local toolchain unreproducible and undiffable."""
    for tool, version in load(MISE)["tools"].items():
        assert version not in ("latest", "*"), f"{tool} is not pinned"
        parse_version(version)


@pytest.mark.parametrize("specifier", ["~=1.0", "!=1.0", "1.0", ""])
def test_satisfies_refuses_an_operator_it_cannot_evaluate(specifier):
    """The guard must not pass a constraint it does not understand."""
    with pytest.raises(ValueError, match="unrecognized version specifier"):
        satisfies("1.0.0", specifier)


@pytest.mark.parametrize(
    "version,specifier,expected",
    [
        ("0.11.29", ">=0.10", True),
        ("0.9.0", ">=0.10", False),
        ("0.10", ">=0.10", True),
        ("0.10.0", ">0.10", False),
        ("1.0.0", "==1.0", True),
    ],
)
def test_satisfies_compares_across_differing_component_counts(
    version, specifier, expected
):
    assert satisfies(version, specifier) is expected
