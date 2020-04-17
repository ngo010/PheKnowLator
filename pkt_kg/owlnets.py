#!/usr/bin/env python
# -*- coding: utf-8 -*-

# import needed libraries
import glob
import networkx   # type: ignore
import os
import os.path
import pickle

from collections import Counter
from rdflib import Graph, BNode, Literal, URIRef   # type: ignore
from tqdm import tqdm  # type: ignore
from typing import Any, Dict, IO, List, Optional, Set, Tuple

from pkt_kg.utils import adds_edges_to_graph, gets_ontology_classes


class OwlNets(object):
    """Class removes OWL semantics from an ontology or knowledge graph using the OWL-NETS method.

    OWL Semantics are nodes and edges in the graph that are needed in order to create a rich semantic representation
    and to do things like run reasoners. Many of these nodes and edges are not clinically or biologically meaningful.
    This class is designed to decode all owl-encoded classes and return a knowledge graph that is semantically rich and
    clinically and biologically meaningful.

    Attributes:
        knowledge_graph: An RDFLib object.
        uuid_map: A dictionary that stores the mapping between each class and its instance.
        write_location: A file path used for writing knowledge graph data.
        res_dir: A string pointing to the 'resources' directory.
        full_kg: A string containing the filename for the full knowledge graph.
        nx_mdg: A networkx graph object that contains the same edges as knowledge_graph.
        keep_properties: A list of owl:Property types to keep when filtering triples from knowledge graph.
        class_list: A list of owl classes from the input knowledge graph.

    Raises:
        TypeError: If graph is not an rdflib.graph object.
        ValueError: If graph is an empty rdflib.graph object.
        TypeError: If the file containing owl object properties is not a txt file.
        TypeError: If the file containing owl object properties is empty.
    """

    def __init__(self, graph: Graph, write_location: str, full_kg: str) -> None:

        self.write_location = write_location
        self.res_dir = os.path.relpath('/'.join(self.write_location.split('/')[:-1]))
        self.full_kg = full_kg

        # verify input graphs
        if not isinstance(graph, Graph):
            raise TypeError('graph must be an RDFLib Graph Object.')
        elif len(graph) == 0:
            raise ValueError('graph is empty.')
        else:
            self.graph = graph

        # convert RDF graph to multidigraph
        print('\nConverting knowledge graph to MultiDiGraph. Note, this process can take up to 20 minutes.')
        self.nx_mdg: networkx.MultiDiGraph = networkx.MultiDiGraph()

        for s, p, o in tqdm(self.graph):
            self.nx_mdg.add_edge(s, o, **{'key': p})

        # set a list of owl:Property types to keep when filtering triples from knowledge graph
        if '.txt' not in glob.glob(self.res_dir + '/owl_decoding/*Property*')[0]:
            raise TypeError('The owl properties file is not type .txt')
        elif os.stat(glob.glob(self.res_dir + '/owl_decoding/*Property*.txt')[0]).st_size == 0:
            file_path = glob.glob(self.res_dir + '/owl_decoding/*Property*.txt')[0]
            raise TypeError('The input file: {} is empty'.format(file_path))
        else:
            with open(glob.glob(self.res_dir + '/owl_decoding/*Property*.txt')[0], 'r') as filepath:  # type: IO[Any]
                self.keep_properties = [x.strip('\n') for x in filepath.readlines() if x]

        # get all classes in knowledge graph
        self.class_list: List = list(gets_ontology_classes(self.graph))

    def removes_edges_with_owl_semantics(self) -> Tuple[Graph, Graph]:
        """Creates a filtered knowledge graph, such that all triples that contained entities needed to support owl
        semantics have been removed. For example:

            REMOVE - edge needed to support owl semantics that are not biologically meaningful:
                subject: http://purl.obolibrary.org/obo/CLO_0037294
                predicate: owl:AnnotationProperty
                object: rdf:about="http://purl.obolibrary.org/obo/CLO_0037294"

            KEEP - biologically meaningful edges:
                subject: http://purl.obolibrary.org/obo/CHEBI_16130
                predicate: http://purl.obolibrary.org/obo/RO_0002606
                object: http://purl.obolibrary.org/obo/HP_0000832

        Returns:
            filtered_graph: An RDFLib graph that contains triples without owl semantics.
            owl_graph: An RDFLib graph that contains edges with owl semantics.
        """

        print('\nFiltering Triples')

        filtered_graph = Graph()

        for predicate in tqdm(self.keep_properties):
            # get list of triples that include the predicate
            triples_to_keep = list(self.graph.triples((None, URIRef(predicate), None)))
            new_edges = [x for x in triples_to_keep if isinstance(x[0], URIRef) and isinstance(x[2], URIRef)]

            # add kept edges to filtered graph
            filtered_graph = adds_edges_to_graph(filtered_graph, new_edges)

        # subset graph to include only triples that were removed
        owl_graph: Graph = self.graph - filtered_graph

        return filtered_graph, owl_graph

    def recurses_axioms(self, seen_nodes: List[BNode], axioms: List[Any]) -> List[BNode]:
        """Function recursively searches a list of knowledge graph nodes and tracks the nodes it has visited. Once
        it has visited all nodes in the input axioms list, a final unique list of relevant nodes is returned. This
        list is assumed to include all necessary nodes needed to re-create an OWL:equivalentClass.

        Args:
            seen_nodes: A list which may or may not contain knowledge graph nodes.
            axioms: A list of axioms, e.g. [(rdflib.term.BNode('N3e23fe5f05ff4a7d992c548607c86277'),
                                            rdflib.term.URIRef('http://www.w3.org/2002/07/owl#Class'),
                                            rdflib.term.URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type'))]

        Returns:
            seen_nodes: A list of knowledge graph nodes.
        """

        search_axioms: List = []
        tracked_nodes: List = []

        for axiom in axioms:
            for element in axiom:
                if isinstance(element, BNode) and element not in seen_nodes:
                    tracked_nodes.append(element)
                    search_axioms += list(self.nx_mdg.out_edges(element, keys=True))

        if len(tracked_nodes) > 0:
            seen_nodes += list(set(tracked_nodes))
            return self.recurses_axioms(seen_nodes, search_axioms)
        else:
            return seen_nodes

    def creates_edge_dictionary(self, node: URIRef) -> Tuple[Dict, Set]:
        """Creates a nested edge dictionary from an input class node by obtaining all of the edges that come
        out from the class and then recursively looping over each anonymous out edge node. The outer
        dictionary keys are anonymous nodes and the inner keys are owl:ObjectProperty values from each out
        edge triple that comes out of that anonymous node. For example:
            {rdflib.term.BNode('N3243b60f69ba468687aa3cbe4e66991f'): {
                someValuesFrom': rdflib.term.URIRef('http://purl.obolibrary.org/obo/PATO_0000587'),
                type': rdflib.term.URIRef('http://www.w3.org/2002/07/owl#Restriction'),
                onProperty': rdflib.term.URIRef('http://purl.obolibrary.org/obo/RO_0000086')
                                                                      }
            }

        While creating the dictionary, if cardinality is used then a formatted string that contains the class node
        and the anonymous node naming the element that includes cardinality is constructed and added to a set.

        Args:
            node: An rdflib.term object.

        Returns:
            class_edge_dict: A nested dictionary. The outer dictionary keys are anonymous nodes and the inner keys
                are owl:ObjectProperty values from each out edge triple that comes out of that anonymous node. An
                example of the dictionaries contents are shown above.
            cardinality: A set of strings, where each string is formatted such that the substring that occurs before
                the ':' is the class node and the substring after the ':' is the anonymous node naming the element where
                cardinality was used.
        """

        matches: List = []
        class_edge_dict: Dict = dict()
        cardinality: Set = set()

        # get all edges that come out of class node
        out_edges = [x for axioms in list(self.nx_mdg.out_edges(node, keys=True)) for x in axioms]

        # recursively loop over anonymous nodes in out_edges to create a list of relevant edges to rebuild class
        for axiom in out_edges:
            if isinstance(axiom, BNode):
                for element in self.recurses_axioms([], list(self.nx_mdg.out_edges(axiom, keys=True))):
                    matches += list(self.nx_mdg.out_edges(element, keys=True))

        # create dictionary of edge lists
        for match in matches:
            if 'cardinality' in str(match[2]).lower():
                cardinality |= {'{}: {}'.format(node, match[0])}
                pass
            else:
                if match[0] in class_edge_dict:
                    class_edge_dict[match[0]][match[2].split('#')[-1]] = {}
                    class_edge_dict[match[0]][match[2].split('#')[-1]] = match[1]
                else:
                    class_edge_dict[match[0]] = {}
                    class_edge_dict[match[0]][match[2].split('#')[-1]] = match[1]

        return class_edge_dict, cardinality

    @staticmethod
    def returns_object_property(sub: URIRef, obj: URIRef, prop: URIRef = None) -> URIRef:
        """Checks the subject and object node types in order to return the correct type of owl:ObjectProperty. The
        following ObjectProperties are returned for each of the following subject-object types:
            - sub + obj are not PATO terms + prop is None --> rdfs:subClassOf
            - sub + obj are PATO terms + prop is None --> rdfs:subClassOf
            - sub is not a PATO term, but obj is a PATO term --> owl:RO_000086
            - sub is a PATO term + obj is a PATO term + prop is not None --> prop

        Args:
            sub: An rdflib.term object.
            obj: An rdflib.term object.
            prop: An rdflib.term object, which is provided as the value of owl:onProperty.

        Returns:
            An rdflib.term object that represents an owl:ObjectProperty.
        """

        if ('PATO' in sub and 'PATO' in obj) and not prop:
            return URIRef('http://www.w3.org/2000/01/rdf-schema#subClassOf')
        elif ('PATO' not in sub and 'PATO' not in obj) and not prop:
            return URIRef('http://www.w3.org/2000/01/rdf-schema#subClassOf')
        elif 'PATO' not in sub and 'PATO' in obj:
            return URIRef('http://purl.obolibrary.org/obo/RO_0000086')
        else:
            return prop

    @staticmethod
    def parses_anonymous_axioms(edges: Dict, class_dict: Dict) -> Dict:
        """Parses axiom dictionaries that only include anonymous axioms (i.e. 'first' and 'rest') and returns an
        updated axiom dictionary that contains owl:Restrictions or an owl constructor (i.e. owl:unionOf or
        owl:intersectionOf).

        Args:
            edges: A subset of dictionary where keys are owl:Objects (i.e. 'first', 'rest', 'onProperty',
                or 'someValuesFrom').
            class_dict: A nested dictionary. The outer dictionary keys are anonymous nodes and the inner keys
                are owl:ObjectProperty values from each out edge triple that comes out of that anonymous node.

        Returns:
             updated_edges: A subset of dictionary where keys are owl:Objects (i.e. 'first', 'rest', 'onProperty',
                or 'someValuesFrom').
        """

        if isinstance(edges['first'], URIRef) and isinstance(edges['rest'], BNode):
            return class_dict[edges['rest']]
        elif isinstance(edges['first'], URIRef) and isinstance(edges['rest'], URIRef):
            return class_dict[edges['first']]
        elif isinstance(edges['first'], BNode) and isinstance(edges['rest'], URIRef):
            return class_dict[edges['first']]
        else:
            return {**class_dict[edges['first']], **class_dict[edges['rest']]}

    def parses_constructors(self, node: URIRef, edges: Dict, class_dict: Dict, relation: URIRef = None)\
            -> Tuple[Set, Optional[Dict]]:
        """Traverses a dictionary of rdflib objects used in the owl:unionOf or owl:intersectionOf constructors, from
        which the original set of edges used to the construct the class_node are edited, such that all owl-encoded
        information is removed. Examples of the transformations performed for these constructor types are shown below:
            - owl:unionOf: CL_0000995, turns into:
                - CL_0000995, rdfs:subClassOf, CL_0001021
                - CL_0000995, rdfs:subClassOf, CL_0001026
            - owl:intersectionOf: PR_000050170, turns into:
                - PR_000050170, rdfs:subClassOf, GO_0071738
                - PR_000050170, RO_0002160, NCBITaxon_9606

        Args:
            node: An rdflib term of type URIRef or BNode that references an OWL-encoded class.
            edges: A subset of dictionary where keys are owl:Objects (i.e. 'first', 'rest', 'onProperty',
                or 'someValuesFrom').
            class_dict: A nested dictionary. The outer dictionary keys are anonymous nodes and the inner keys
                are owl:ObjectProperty values from each out edge triple that comes out of that anonymous node.
            relation: An rdflib.URIRef object that defaults to None, but if provided by a user contains an
                owl:onProperty relation.

        Returns:
            cleaned_classes: A list of tuples, where each tuple represents a class which has had the OWL semantics
                removed.
             edge_batch: A subset of dictionary where keys are owl:Objects (i.e. 'first', 'rest', 'onProperty',
                or 'someValuesFrom').
        """

        cleaned_classes: Set = set()
        edge_batch = class_dict[edges['unionOf' if 'unionOf' in edges.keys() else 'intersectionOf']]

        while edge_batch:
            if ('first' in edge_batch.keys() and 'rest' in edge_batch.keys()) and 'type' not in edge_batch.keys():
                if isinstance(edge_batch['first'], URIRef) and isinstance(edge_batch['rest'], BNode):
                    obj_property = self.returns_object_property(node, edge_batch['first'], relation)
                    cleaned_classes |= {(node, obj_property, edge_batch['first'])}
                    edge_batch = class_dict[edge_batch['rest']]
                elif isinstance(edge_batch['first'], URIRef) and isinstance(edge_batch['rest'], URIRef):
                    obj_property = self.returns_object_property(node, edge_batch['first'], relation)
                    cleaned_classes |= {(node, obj_property, edge_batch['first'])}
                    edge_batch = None
                else:
                    edge_batch = self.parses_anonymous_axioms(edge_batch, class_dict)
            else:
                break

        return cleaned_classes, edge_batch

    def parses_restrictions(self, node: URIRef, edges: Dict, class_dict: Dict) -> Tuple[Set, Optional[Dict]]:
        """Parses a subset of a dictionary containing rdflib objects participating in a constructor (i.e.
        owl:intersectionOf or owl:unionOf) and reconstructs the class (referenced by node) in order to remove
        owl-encoded information. An example is shown below:
            - owl:restriction PR_000050170, turns into: (PR_000050170, RO_0002180, PR_000050183)

        Args:
            node: An rdflib term of type URIRef or BNode that references an OWL-encoded class.
            edges: A subset of dictionary where keys are owl:Objects (e.g. 'first', 'rest', 'onProperty',
                'onClass', or 'someValuesFrom').
            class_dict: A nested dictionary. The outer dictionary keys are anonymous nodes and the inner keys
                are owl:ObjectProperty values from each out edge triple that comes out of that anonymous node.

        Returns:
             cleaned_classes: A list of tuples, where each tuple represents a class which has had the OWL semantics
                removed.
             edge_batch: A subset of dictionary where keys are owl:Objects (e.g. 'first', 'rest', 'onProperty',
                'onClass', or 'someValuesFrom').
        """

        cleaned_classes: Set = set()
        edge_batch = edges
        object_type = [x for x in edge_batch.keys() if x not in ['type', 'first', 'rest', 'onProperty']][0]

        if isinstance(edge_batch[object_type], URIRef) or isinstance(edge_batch[object_type], Literal):
            object_node = node if object_type == 'hasSelf' else edge_batch[object_type]

            if len(edge_batch) == 3:
                cleaned_classes |= {(node, edge_batch['onProperty'], object_node)}
                return cleaned_classes, None
            else:
                cleaned_classes |= {(node, edge_batch['onProperty'], object_node)}
                return cleaned_classes, self.parses_anonymous_axioms(edge_batch, class_dict)
        else:
            axioms = class_dict[edge_batch[object_type]]

            if 'unionOf' in axioms.keys() or 'intersectionOf' in axioms.keys():
                results = self.parses_constructors(node, axioms, class_dict, edge_batch['onProperty'])
                cleaned_classes |= results[0]
                return cleaned_classes, results[1]
            else:
                return cleaned_classes, axioms

    def cleans_owl_encoded_classes(self) -> Graph:
        """Loops over a list of owl classes in a knowledge graph searching for edges that include owl:equivalentClass
        nodes (i.e. to find classes assembled using owl constructors) and rdfs:subClassof nodes (i.e. to find
        owl:restrictions). Once these edges are found, the method loops over the in and out edges of anonymous nodes
        in the edges in order to eliminate the owl-encoded nodes.

        Returns:
            # cleaned_class_dict: A dictionary where keys are owl-encoded nodes and values are a set of tuples, where
            #     where each tuple represents a triple which has had the OWL semantics removed. This dictionary is also
            #     saved locally.
            decoded_graph: An RDFLib graph object that contains only cleaned decoded owl classes.
        """

        print('\nDecoding OWL Constructors and Restrictions')

        decoded_graph: Graph = Graph()
        cleaned_nodes: Set = set()
        complement_constructors: Set = set()
        cardinality: Set = set()
        misc: List = []

        pbar = tqdm(total=len(self.class_list))

        while self.class_list:
            pbar.update(1)
            node = self.class_list.pop(0)
            node_information = self.creates_edge_dictionary(node)
            class_edge_dict = node_information[0]
            cardinality |= node_information[1]

            if len(class_edge_dict) == 0:
                pass
            elif any(v for v in class_edge_dict.values() if 'complementOf' in v.keys()):
                complement_constructors |= {node}
                pass
            else:
                cleaned_nodes |= {node}
                cleaned_classes: Set = set()
                semantic_chunk = [x[1] for x in list(self.nx_mdg.out_edges(node, keys=True)) if isinstance(x[1], BNode)]

                # decode owl-encoded edges
                for element in semantic_chunk:
                    edges = class_edge_dict[element]

                    while edges:
                        if 'unionOf' in edges.keys():
                            results = self.parses_constructors(node, edges, class_edge_dict)
                            cleaned_classes |= results[0]
                            edges = results[1]
                        elif 'intersectionOf' in edges.keys():
                            results = self.parses_constructors(node, edges, class_edge_dict)
                            cleaned_classes |= results[0]
                            edges = results[1]
                        elif 'Restriction' in edges['type']:
                            results = self.parses_restrictions(node, edges, class_edge_dict)
                            cleaned_classes |= results[0]
                            edges = results[1]
                        else:
                            # catch all other axioms -- only catching owl:onProperty with owl:oneOf
                            misc += [x for x in edges.keys() if x not in ['type', 'first', 'rest', 'onProperty']]
                            edges = None

                # add kept edges to filtered graph
                decoded_graph = adds_edges_to_graph(decoded_graph, list(cleaned_classes))

        pbar.close()

        # delete networkx graph object to free up memory
        del self.nx_mdg

        print('=' * 75)
        print('Decoded {} owl-encoded classes. Note the following:'.format(len(cleaned_nodes)))
        print('{} owl class elements containing cardinality were ignored'.format(len(cardinality)))
        print('ignored {} misc classes of the following type(s): {}'.format(len(misc), ', '.join(list(Counter(misc)))))
        print('{} owl classes constructed using owl:complementOf were removed'.format(len(complement_constructors)))
        print('=' * 75)

        return decoded_graph

    def run_owl_nets(self) -> Graph:
        """Adds triples from a dictionary containing a set of decoded triples to an rdflib.graph.

        Returns:
            An rdflib.Graph object that has been updated to only include triples owl decoded triples.
        """

        print('\nCreating OWL-NETS graph')

        # filter out owl-encoded triples from original knowledge graph
        filtered_graph, owl_graph = self.removes_edges_with_owl_semantics()

        # clean constructors and restrictions
        self.graph = self.cleans_owl_encoded_classes()
        decoded_no_owl, decoded_owl = self.removes_edges_with_owl_semantics()  # filter out owl-encoded

        # creating owl nets graphs
        owl_nets_graph = filtered_graph + decoded_no_owl  # combine cleaned triples and decoded owl graphs
        owl_nets_owl_graph = owl_graph + decoded_owl  # combine graphs owl-nets filtered information

        # write out graph containing owl semantic edges
        file_name = self.write_location + '/' + self.full_kg[:-4] + '_OWLNets_BiProduct.nt'
        owl_nets_owl_graph.serialize(destination=file_name, format='nt')

        # print kg statistics
        edges = len(set(list(owl_nets_graph)))
        nodes = len(set([str(node) for edge in list(owl_nets_graph) for node in edge[0::2]]))
        print('Completed the Removal of OWL Semantics')
        print('The Decoded Knowledge graph contains: {node} nodes and {edge} edges\n'.format(node=nodes, edge=edges))

        return owl_nets_graph
