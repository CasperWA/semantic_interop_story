from collections import defaultdict
import types
from typing import Tuple, List, Any
from pydantic.dataclasses import dataclass
from rdflib import Graph as RDFGraph
from graphviz import Digraph

NTuple = Tuple[Any, ...]


@dataclass
class Graph:
    triples: List[Tuple[Any, ...]]

    def clear(self):
        self.triples.clear()

    def append(self, nt: NTuple):
        if not nt in self.triples:
            self.triples.append(nt)

    def match(self, s=None, p=None, o=None):
        for t in self.triples:
            if (not s or t[0] == s) and (not p or t[1] == p) and (not o or t[2] == o):
                yield t

    def parse(self, uri, fmt="ttl"):
        g = RDFGraph().parse(uri, format=fmt)
        for s, p, o in g.triples((None, None, None)):
            self.append((s, p, o))

    def path(self, origin, destination, link=None, visited=None):
        if link is None:
            link = [origin]
        if visited is None:
            visited = []

        visited.append(origin)
        for _, _, dest in self.match(origin, None, None):
            if not dest in visited:
                link.append(dest)
                print("forward", dest)
                if dest == destination:
                    return link
                return self.path(dest, destination, link, visited)

        for dest, _, _ in self.match(None, None, origin):
            if not dest in visited:
                link.append(dest)
                print("reverse", dest)
                if dest == destination:
                    return link
                return self.path(dest, destination, link, visited)

    def plot(self):
        """
        Create Digraph plot
        """
        dot = Digraph()
        # Add nodes 1 and 2
        for s, p, o in self.match():
            dot.node(str(s))
            dot.node(str(o))
            dot.edge(str(s), str(o), label=p)

        # Visualize the graph
        return dot


def mapping_route(
        target, sources, triples,
        mapsTo=':mapsTo',
        subClassOf='http://www.w3.org/2000/01/rdf-schema#subClassOf',
        subPropertyOf='http://www.w3.org/2000/01/rdf-schema#subPropertyOf',
):
    """Finds the route of mappings from any source in `sources` to `target`.
    This implementation takes transitivity, subclasses and
    subproperties into accaount.

    Args:
        target: IRI of the target in `triples`.
        sources: Sequence of source IRIs in `triples`.
        triples: Sequence of (subject, predicate, object) triples.
          It is safe to pass a generator expression too.
        mapsTo: How 'mapsTo' is written in `triples`.
        subClassOf: How 'subClassOf' is written in `triples`.  Set it
          to None if subclasses should not be considered.
        subPropertyOf: How 'subPropertyOf' is written in `triples`.  Set it
          to None if subproperties of `mapsTo` should not be considered.
        hasInput: How 'hasInput' is written in `triples`.
        hasOutput: How 'hasOutput' is written in `triples`.

    Returns:
        list: Names of all sources that maps to `target`.
        list: A nested list with different mapping routes from `target`
          to a source, where a mapping route is expressed as a
          list of triples.  For example:
              [(target, mapsTo, 'onto:A'),
               ('onto:A', mapsTo, 'onto:B'),
               (source1, mapsTo, 'onto:B')]

    Bugs:
        In the current implementation will the returned mapping route
        report sub properties of `mapsTo` as `mapsTo`.  Some
        postprocessing is required to fix this.

    """
    sources = set(sources)

    # Create a set of 'relations' to consider, consisting of mapsTo and
    # its sub properties
    if subPropertyOf:
        def walk(src, d):
            yield src
            for s in d[src]:
                yield from walk(s, d)

        def get_relations(rel):
            """Returns a set of `rel` and its subproperties."""
            oSPs = defaultdict(set)
            for s, p, o in triples:
                if p == subPropertyOf:
                    oSPs[o].add(s)
            return set(walk(rel, oSPs))

        if isinstance(triples, types.GeneratorType):
            # Convert generator to a list such that we can transverse it twice
            triples = list(triples)

        #oSPs = defaultdict(set)  # (o, subPropertyOf, s) ==> oSPs[o] -> {s, ..}
        #for s, p, o in triples:
        #    if p == subPropertyOf:
        #        oSPs[o].add(s)
        #relations = set(walk(mapsTo, oSPs))
        #del oSPs
        relations = get_relations(mapsTo)
    else:
        relations = set([mapsTo])

    # Create lookup tables for fast access to properties
    # This only transverse `tiples` once
    sRo = defaultdict(list)   # (s, mapsTo, o)     ==> sRo[s] -> [o, ..]
    oRs = defaultdict(list)   # (o, mapsTo, s)     ==> oRs[o] -> [s, ..]
    sSCo = defaultdict(list)  # (s, subClassOf, o) ==> sSCo[s] -> [o, ..]
    oSCs = defaultdict(list)  # (o, subClassOf, s) ==> oSCs[o] -> [s, ..]
    for s, p, o in triples:
        if p in relations:
            sRo[s].append(o)
            oRs[o].append(s)
        elif p == subClassOf:
            sSCo[s].append(o)
            oSCs[o].append(s)

    # The lists to return, populated with walk_forward() and walk_backward()
    mapped_sources = []
    mapped_routes = []

    def walk_forward(entity, visited, route):
        """Walk forward from `entity` in the direction of mapsTo."""
        if entity not in visited:
            walk_backward(entity, visited, route)
            for e in sRo[entity]:
                walk_forward(
                    e, visited.union(set([entity])),
                    route + [(entity, mapsTo, e)])
            for e in oSCs[entity]:
                walk_forward(
                    e, visited.union(set([entity])),
                    route + [(e, subClassOf, entity)])

    def walk_backward(entity, visited, route):
        """Walk backward from `entity` to a source, against the direction of
        mapsTo."""
        if entity not in visited:
            if entity in sources:
                mapped_sources.append(entity)
                mapped_routes.append(route)
            else:
                for e in oRs[entity]:
                    walk_backward(
                        e, visited.union(set([entity])),
                        route + [(e, mapsTo, entity)])
                for e in sSCo[entity]:
                    walk_backward(
                        e, visited.union(set([entity])),
                        route + [(entity, subClassOf, e)])

    walk_forward(target, set(), [])

    return mapped_sources, mapped_routes
