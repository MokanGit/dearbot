#!/usr/bin/env python3
"""Verify that the reviewed Python lock satisfies every direct requirement."""

from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
DIRECT_FILE = ROOT / "backend" / "requirements.in"
LOCK_FILE = ROOT / "backend" / "requirements.txt"


def load_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            requirements.append(Requirement(line))
        except ValueError as exc:
            raise SystemExit(f"{path}:{line_number}: unsupported requirement: {exc}") from exc
    return requirements


def main() -> None:
    direct = load_requirements(DIRECT_FILE)
    locked_requirements = load_requirements(LOCK_FILE)
    locked: dict[str, Version] = {}

    for requirement in locked_requirements:
        pins = [specifier for specifier in requirement.specifier if specifier.operator == "=="]
        if len(pins) != 1 or len(requirement.specifier) != 1:
            raise SystemExit(f"{LOCK_FILE}: {requirement.name} must have one exact == pin")
        locked[canonicalize_name(requirement.name)] = Version(pins[0].version)

    errors: list[str] = []
    for requirement in direct:
        name = canonicalize_name(requirement.name)
        version = locked.get(name)
        if version is None:
            errors.append(f"{requirement.name} is missing from {LOCK_FILE}")
        elif version not in requirement.specifier:
            errors.append(
                f"{requirement.name}=={version} does not satisfy {requirement.specifier}"
            )

    if errors:
        raise SystemExit("Python dependency lock is inconsistent:\n- " + "\n- ".join(errors))

    print(f"Verified {len(direct)} direct dependencies against {LOCK_FILE}")


if __name__ == "__main__":
    main()
