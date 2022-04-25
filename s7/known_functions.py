from typing import Any, Iterable


def doubles(data: Iterable[Any]) -> list[Any]:
    """Doubles whatever is in `data`."""
    return [2 * _ for _ in data]


def halves(data: Iterable[Any]) -> list[Any]:
    """Halves whatever is in `data`."""
    return [_ / 2 for _ in data]


def imp_to_flux(impendance_ohm: Iterable[float]) -> float:
    return doubles(impendance_ohm)


def cas_to_smiles(cas_number: Iterable[str]) -> str:
    return [f"{_}" + "-SMILES_NOW" for _ in cas_number]
