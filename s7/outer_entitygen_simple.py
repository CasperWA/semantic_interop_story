"""Generate SOFT7 (outer mapping) entities based on basic information:

1. SOFT7 entity data model.
2. Semantic Mapping.
3. Internal data source SOFT7 entity.

"""
from enum import Enum
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from oteapi.models import ResourceConfig
from otelib import OTEClient
from pydantic import create_model, Field
import yaml

from s7 import known_functions
from .models import SOFT7DataEntity
from .graph import Graph

TEST_KNOWLEDGE_BASE = Graph(
    [
        ("imp_to_flux", "isA", "function"),
        ("imp_to_flux", "expects", "ImpedanceOhm"),
        ("imp_to_flux", "outputs", "EISEfficiency"),
        ("ImpedanceOhm", "isA", "Resistance"),
        ("ImpedanceLogOhm", "isA", "Resistance"),
        ("EISEfficiency", "isA", "InhibitorEfficiency"),
        ("LPREfficiency", "isA", "InhibitorEfficiency"),
        ("Resistance", "isA", "Parameter"),
        ("InhibitorEfficiency", "isA", "Output"),
        ("cas_to_smiles", "isA", "function"),
        ("cas_to_smiles", "expects", "CAS#"),
        ("cas_to_smiles", "outputs", "SMILES"),
    ]
)


class HashableResourceConfig(ResourceConfig):
    """ResourceConfig, but hashable."""

    def __hash__(self) -> int:
        return hash(
            tuple(
                (field_name, field_value)
                if isinstance(field_value, (str, bytes, tuple, frozenset, int, float)) or field_value is None
                else (field_name, None)
                for field_name, field_value in self.__dict__.items()
            )
        )


class SOFT7EntityPropertyType(str, Enum):
    """Property type enumeration."""

    STR = "string"
    FLOAT = "float"

    @property
    def py_cls(self) -> type:
        """Get the equivalent Python cls."""
        return {
            self.STR: str,
            self.FLOAT: float,
        }[self]


@lru_cache
def _get_property(name: str, config: HashableResourceConfig, url: Optional[str] = None) -> Any:
    """Get a property."""
    client = OTEClient(url or "http://localhost:8080")
    try:
        data_resource = client.create_dataresource(**config.dict())
    except Exception as exc:
        raise AttributeError(f"{name!r} could not be determined") from exc
    result: dict[str, Any] = json.loads(data_resource.get())
    if name in result:
        return result[name]
    raise AttributeError(f"{name!r} could not be determined")


def _get_property_local(
    graph: Graph,
) -> Any:
    """Get a property - local."""
    # Not found in cache - go get property
    # path = graph.path("")

    _temp_results = {
        "SMILES": [function_ for _, _, function_ in graph.match(s="cas_to_smiles", p="executes")][0],
        "inhibitorEfficiency": [function_ for _, _, function_ in graph.match(s="imp_to_flux", p="executes")][0]
    }
    _temp_paths = {
        "SMILES": ["SMILES", "cas_to_smiles", "CAS#", "inner.casNumber"],
        "inhibitorEfficiency": ["EISEfficiency", "imp_to_flux", "ImpedanceOhm", "inner.impedance_ohm_24h"],
    }

    def __get_property(name: str):
        input_ = [function_ for _, _, function_ in graph.match(s=_temp_paths[name][-1], p="get")][0]
        return _temp_results[name](input_(_temp_paths[name][-1].split(".")[-1]))

    return __get_property


def create_outer_entity(
    data_model: Union[Path, str, dict[str, Any]],
    inner_entity: SOFT7DataEntity,
    mapping: Union[Graph, Iterable[tuple[str, str, str]]],
) -> SOFT7DataEntity:
    """Create and return a SOFT7 entity wrapped as a pydantic model.

    Parameters:
        data_model: A SOFT7 data model entity or a string/path to a YAML file of the
            data model.
        inner_entity: The data source SOFT7 entity.
        mapping: A sequence of RDF triples representing the mapping.

    Returns:
        A SOFT7 entity class wrapped as a pydantic data model.

    """
    if isinstance(data_model, (str, Path)):
        if not Path(data_model).resolve().exists:
            raise FileNotFoundError(f"Could not find a data model YAML file at {data_model!r}")
        data_model: dict[str, Any] = yaml.safe_load(Path(data_model).resolve().read_text(encoding="utf8"))
    if not isinstance(data_model, dict):
        raise TypeError("data_model must be a dict")

    if not isinstance(inner_entity, SOFT7DataEntity):
        raise TypeError("inner_entity must be a SOFT7DataEntity")

    if isinstance(mapping, Iterable):
        mapping = Graph(list(mapping))
    if not isinstance(mapping, Graph):
        raise TypeError("mapping must be a Graph")

    if any(
        property_name.startswith("_")
        for property_name in data_model.get("properties", {})
    ):
        raise ValueError(
            "data model property names may not start with an underscore (_)"
        )

    # Create "complete" local graph
    # local_graph = Graph(
    #     [
    #         ("inner", "isA", "DataSourceEntity"),
    #         ("outer", "isA", "OuterEntity"),
    #         ("DataSourceEntity", "isA", "SOFT7DataEntity"),
    #         ("OuterEntity", "isA", "SOFT7DataEntity"),
    #     ]
    # )
    local_graph = Graph()
    for s, _, _ in mapping.triples:
        split_subject = s.split(".")
        if split_subject[0] == "inner":
            local_graph.append(
                (s, "get", lambda name: getattr(inner_entity, name))
            )

    for triple in TEST_KNOWLEDGE_BASE.triples:
        local_graph.append(triple)

    # Generate lambda functions for properties
    # functions: list[str] = [
    #     function_name for function_name, _, _ in mapping.match(p="isA", o="function")
    # ]
    for function_name, _, _ in local_graph.match(p="isA", o="function"):
        missing_functions = []
        if not hasattr(known_functions, function_name):
            missing_functions.append(function_name)
        else:
            local_graph.append(
                (
                    function_name,
                    "executes",
                    getattr(known_functions, function_name),
                )
            )
        if missing_functions:
            raise ValueError(
                f"{missing_functions} not found in known functions !"
            )

    return create_model(
        "OuterEntity",
        **{
            property_name: (
                SOFT7EntityPropertyType(property_value.get("type", "")).py_cls,
                Field(
                    default_factory=lambda: _get_property_local(local_graph),
                    description=property_value.get("description", ""),
                    title=property_name.replace(" ", "_"),
                    type=SOFT7EntityPropertyType(property_value.get("type", "")).py_cls,
                )
            ) for property_name, property_value in data_model.get("properties", {}).items()
        },
        __module__ = __name__,
        __base__ = SOFT7DataEntity,
    )
