"""Generate SOFT7 (outer mapping) entities based on basic information:

1. SOFT7 entity data model.
2. Semantic Mapping.
3. Internal data source SOFT7 entity.

"""
from enum import Enum
from pathlib import Path
from types import FunctionType
from typing import Any, Iterable, Union, Callable, Optional

from IPython import display
from oteapi.models import ResourceConfig
from pydantic import create_model, Field
import yaml

from s7 import known_functions
from .models import SOFT7DataEntity
from .graph import Graph

TEST_KNOWLEDGE_BASE = Graph(
    [
        ("imp_to_eis", "isA", "function"),
        ("imp_to_eis", "expects", "ImpedanceOhm"),
        ("imp_to_eis", "outputs", "EISEfficiency"),
        ("imp_to_lpr", "isA", "function"),
        ("imp_to_lpr", "expects", "ImpedanceLogOhm"),
        ("imp_to_lpr", "outputs", "LPREfficiency"),
        ("imp_log_func", "isA", "function"),
        ("imp_log_func", "expects", "ImpedanceOhm"),
        ("imp_log_func", "outputs", "ImpedanceLogOhm"),
        ("ImpedanceOhm", "isA", "Resistance"),
        ("ImpedanceLogOhm", "isA", "Resistance"),
        ("EISEfficiency", "isA", "InhibitorEfficiency"),
        ("LPREfficiency", "isA", "InhibitorEfficiency"),
        ("Resistance", "isA", "Parameter"),
        ("InhibitorEfficiency", "isA", "Output"),
        ("cas_to_smiles", "isA", "function"),
        ("cas_to_smiles", "expects", "CASNumber"),
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


def _get_inputs(name: str, graph: Graph) -> Optional[list[tuple[str, FunctionType, str]]]:
    """Retrieve all inputs/parameters for a function ONLY if it comes from internal entity."""
    expects = [
        expect for _, _, expect in graph.match(name, "expects", None)
    ]
    # print(expects)

    inputs: list[str] = []
    for expect in expects:
        mapped_input = [
            input_ for input_, _, _ in graph.match(None, "mapsTo", expect)
        ]
        if len(mapped_input) > 1:
            raise RuntimeError(
                f"Expected exactly 1 mapping to {expect}, instead found {len(mapped_input)} !"
            )
        inputs.extend(mapped_input)
    # print(inputs)
    if not inputs:
        return None

    input_getters = []
    for input_ in inputs:
        mapped_getter = [
            function_ for _, _, function_ in graph.match(input_, "get", None)
        ]
        if len(mapped_getter) > 1:
            raise RuntimeError(
                f"Expected exactly 1 getter function for {input_!r}, instead found {len(mapped_getter)} !"
            )
        input_getters.append(mapped_getter[0])

    return list(
        zip(
            expects,
            input_getters,
            [input_.split(".")[-1] for input_ in inputs],
        )
    )


def _get_property_local(
    graph: Graph,
) -> Callable[[str], Any]:
    """Get a property - local."""
    predicate_filter = ["mapsTo", "outputs", "expects", "hasProperty"]

    def __get_property(name: str) -> Any:
        path = graph.path(f"outer.{name}", "inner", predicate_filter)
        # print(path)
        if len(path) > 1:
            raise RuntimeError("Found more than one path through the graph !")
        path = path[0]

        functions = [
            _ for _ in path
            if _ in [s for s, _, _ in graph.match(None, "isA", "function")]
        ]
        # print(functions)

        if not functions:
            raise RuntimeError(f"No function found to retrieve {name!r}")

        functions_dict: dict[str, dict[str, Any]] = {}
        for function_name in functions:
            functions_dict[function_name] = {
                "inputs": _get_inputs(function_name, graph),
                "function": [
                    function_
                    for _, _, function_ in graph.match(function_name, "executes", None)
                ][0],
            }

        res = None
        for function_name in reversed(functions):
            # print(function_name)
            if functions_dict[function_name]["inputs"]:
                res = functions_dict[function_name]["function"](
                    **{
                        param_name: getter_func(getter_func_param)
                        for param_name, getter_func, getter_func_param in functions_dict[function_name]["inputs"]
                    }
                )
            else:
                res = functions_dict[function_name]["function"](res)
            # print(res)
        return res

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
    local_graph = Graph(
        [
            ("inner", "isA", "DataSourceEntity"),
            ("outer", "isA", "OuterEntity"),
            ("DataSourceEntity", "isA", "SOFT7DataEntity"),
            ("OuterEntity", "isA", "SOFT7DataEntity"),
        ]
    )
    for s, p, o in mapping.triples:
        local_graph.append((s, p, o))
        split_subject = s.split(".")
        if split_subject[0] == "inner":
            for triple in [
                (split_subject[0], "hasProperty", s),
                (s, "get", lambda property_name: getattr(inner_entity, property_name)),
            ]:
                local_graph.append(triple)

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

    display.display(local_graph.plot())

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
