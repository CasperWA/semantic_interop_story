from typing import Any, Iterable

from numpy import log10


def doubles(data: Iterable[Any]) -> list[Any]:
    """Doubles whatever is in `data`."""
    return [2 * _ for _ in data]


def halves(data: Iterable[Any]) -> list[Any]:
    """Halves whatever is in `data`."""
    return [_ / 2 for _ in data]


def imp_to_eis(ImpedanceOhm: Iterable[float]) -> list[float]:
    return doubles(ImpedanceOhm)


def imp_to_lpr(ImpedanceLogOhm: Iterable[float]) -> list[float]:
    return halves(ImpedanceLogOhm)


def cas_to_smiles(CASNumber: Iterable[str]) -> list[str]:
    import cirpy

    return [cirpy.resolve(_, "smiles") for _ in CASNumber]


def imp_log_func(ImpedanceOhm: Iterable[float]) -> list[float]:
    return list(log10(ImpedanceOhm))
