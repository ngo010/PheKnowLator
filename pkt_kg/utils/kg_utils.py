#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Knowledge Graph Utility Functions.

Interacts with OWL Tools API
* gets_ontology_classes
* gets_ontology_statistics
* gets_object_properties
* merges_ontologies
* ontology_file_formatter

Interacts with Knowledge Graphs
* adds_edges_to_graph

Writes Triple Lists
* maps_node_ids_to_integers

File Type Conversion
* converts_rdflib_to_networkx
"""

# import needed libraries
import glob
import json
import networkx  # type: ignore
import os
import os.path
from rdflib import Graph, URIRef  # type: ignore
from rdflib.namespace import RDF, OWL  # type: ignore
import subprocess

from tqdm import tqdm  # type: ignore
from typing import Dict, List, Optional, Set, Tuple


def gets_ontology_classes(graph: Graph) -> Set:
    """Queries a knowledge graph and returns a list of all owl:Class objects in the graph.

    Args:
        graph: An rdflib Graph object.

    Returns:
        class_list: A list of all of the classes in the graph.

    Raises:
        ValueError: If the query returns zero nodes with type owl:ObjectProperty.
    """

    print('\nQuerying Knowledge Graph to Obtain all OWL:Class Nodes')

    # find all classes in graph
    kg_classes = graph.query(
        """SELECT DISTINCT ?c
             WHERE {?c rdf:type owl:Class . }
        """, initNs={'rdf': RDF, 'owl': OWL}
    )

    # convert results to list of classes
    class_list = set([res[0] for res in tqdm(kg_classes) if isinstance(res[0], URIRef)])

    if len(class_list) > 0:
        return class_list
    else:
        raise ValueError('ERROR: No classes returned from query.')


def gets_deprecated_ontology_classes(graph: Graph) -> Set:
    """Queries a knowledge graph and returns a list of all deprecated owl:Class objects in the graph.

    Args:
        graph: An rdflib Graph object.

    Returns:
        class_list: A list of all of the deprecated OWL classes in the graph.

    Raises:
        ValueError: If the query returns zero nodes with type owl:Class.
    """

    print('\nQuerying Knowledge Graph to Obtain all deprecated OWL:Class Nodes')

    # find all classes in graph
    kg_classes = graph.query(
        """SELECT DISTINCT ?c
             WHERE {?c owl:deprecated true . }
        """, initNs={'owl': OWL}
    )

    # convert results to list of classes
    class_list = set([res[0] for res in tqdm(kg_classes) if isinstance(res[0], URIRef)])

    return class_list


def gets_object_properties(graph: Graph) -> Set:
    """Queries a knowledge graph and returns a list of all owl:ObjectProperty objects in the graph.

    Args:
        graph: An rdflib Graph object.

    Returns:
        object_property_list: A list of all of the object properties in the graph.

    Raises:
        ValueError: If the query returns zero nodes with type owl:ObjectProperty.
    """

    print('\nQuerying Knowledge Graph to Obtain all OWL:ObjectProperty Nodes')

    # find all classes in graph
    kg_object_properties = graph.query(
        """SELECT DISTINCT ?p
             WHERE {?p rdf:type owl:ObjectProperty . }
        """, initNs={'rdf': RDF, 'owl': OWL}
    )

    # convert results to list of classes
    object_property_list = set([res[0] for res in tqdm(kg_object_properties) if isinstance(res[0], URIRef)])

    if len(object_property_list) > 0:
        return object_property_list
    else:
        raise ValueError('ERROR: No object properties returned from query.')


def gets_ontology_statistics(file_location: str, owltools_location: str = './pkt_kg/libs/owltools') -> None:
    """Uses the OWL Tools API to generate summary statistics (i.e. counts of axioms, classes, object properties, and
    individuals).

    Args:
        file_location: A string that contains the file path and name of an ontology.
        owltools_location: A string pointing to the location of the owl tools library.

    Returns:
        None.

    Raises:
        TypeError: If the file_location is not type str.
        OSError: If file_location points to a non-existent file.
        ValueError: If file_location points to an empty file.
    """

    if not isinstance(file_location, str):
        raise TypeError('ERROR: file_location must be a string')
    elif not os.path.exists(file_location):
        raise OSError('The {} file does not exist!'.format(file_location))
    elif os.stat(file_location).st_size == 0:
        raise ValueError('FILE ERROR: input file: {} is empty'.format(file_location))
    else:
        output = subprocess.check_output([os.path.abspath(owltools_location), file_location, '--info'])

    # print stats
    res = output.decode('utf-8').split('\n')[-5:]
    cls, axs, op, ind = res[0].split(':')[-1], res[3].split(':')[-1], res[2].split(':')[-1], res[1].split(':')[-1]
    sent = '\nThe knowledge graph contains {0} classes, {1} axioms, {2} object properties, and {3} individuals\n'

    print(sent.format(cls, axs, op, ind))

    return None


def merges_ontologies(ontology_files: List[str], write_location: str, merged_ont_kg: str,
                      owltools_location: str = './pkt_kg/libs/owltools') -> Graph:
    """Using the OWLTools API, each ontology listed in in the ontologies attribute is recursively merged with into a
    master merged ontology file and saved locally to the provided file path via the merged_ontology attribute. The
    function assumes that the file is written to the directory specified by the write_location attribute.

    Args:
        ontology_files: A list of ontology file paths.
        write_location: A string pointing to a local directory for writing data.
        merged_ont_kg: A string pointing to the location of the merged ontology file.
        owltools_location: A string pointing to the location of the owl tools library.

    Returns:
        None.
    """

    if not ontology_files:
        return None
    else:
        if write_location + merged_ont_kg in glob.glob(write_location + '/*.owl'):
            ont1, ont2 = ontology_files.pop(), write_location + merged_ont_kg
        else:
            ont1, ont2 = ontology_files.pop(), ontology_files.pop()

        try:
            print('\nMerging Ontologies: {ont1}, {ont2}'.format(ont1=ont1.split('/')[-1], ont2=ont2.split('/')[-1]))

            subprocess.check_call([os.path.abspath(owltools_location), str(ont1), str(ont2),
                                   '--merge-support-ontologies',
                                   '-o', write_location + merged_ont_kg])
        except subprocess.CalledProcessError as error:
            print(error.output)

        return merges_ontologies(ontology_files, write_location, merged_ont_kg)


def ontology_file_formatter(write_location: str, full_kg: str, owltools_location: str = './pkt_kg/libs/owltools') -> \
        None:
    """Reformat an .owl file to be consistent with the formatting used by the OWL API. To do this, an ontology
    referenced by graph_location is read in and output to the same location via the OWLTools API.

    Args:
        write_location: A string pointing to a local directory for writing data.
        full_kg: A string containing the subdirectory and name of the the knowledge graph file.
        owltools_location: A string pointing to the location of the owl tools library.

    Returns:
        None.

    Raises:
        TypeError: If something other than an .owl file is passed to function.
        IOError: If the graph_location file is empty.
        TypeError: If the input file contains no data.
    """

    print('\n*** Applying OWL API Formatting to Knowledge Graph OWL File ***')
    graph_write_location = write_location + full_kg

    # check input owl file
    if '.owl' not in graph_write_location:
        raise TypeError('ERROR: The provided file is not type .owl')
    elif not os.path.exists(graph_write_location):
        raise IOError('The {} file does not exist!'.format(graph_write_location))
    elif os.stat(graph_write_location).st_size == 0:
        raise TypeError('ERROR: input file: {} is empty'.format(graph_write_location))
    else:
        try:
            subprocess.check_call([os.path.abspath(owltools_location),
                                   graph_write_location,
                                   '-o', graph_write_location])
        except subprocess.CalledProcessError as error:
            print(error.output)

    return None


def adds_edges_to_graph(graph: Graph, edge_list: List) -> Graph:
    """Takes a tuple of tuples representing new triples and adds them to a knowledge graph. At the same time,
    a list, meant to track all new edges added to the knowledge graph is updated.

    Args:
        graph: An RDFLib Graph object.
        edge_list: A list of tuples, where each tuple contains a triple.

    Returns:
        graph: An updated RDFLib graph.
    """

    for edge in set(edge_list):
        graph.add(edge)  # add edge to knowledge graph

    return graph


def finds_node_type(edge_info: Dict) -> Dict:
    """Takes a dictionary of edge information and parses the data type for each node in the edge. The function
    returns either None or a string containing a particular node from the edge.

    Args:
        edge_info: A dict of information needed to add edge to graph, for example:
            {'n1': 'subclass', 'n2': 'class','relation': 'RO_0003302',
            'url': ['https://www.ncbi.nlm.nih.gov/gene/', 'http://purl.obolibrary.org/obo/'],
            'edges': ['2', 'DOID_0110035']}

    Returns:
        A dictionary with 4 keys representing node type (i.e. "cls1", "cls2", "ent1", and "ent2") and values are
        strings containing a concatenation of the uri and the node. An example of a class-class edge is shown below:
            {'cls1': 'http://purl.obolibrary.org/obo/CHEBI_81395',
            'cls2': 'http://purl.obolibrary.org/obo/DOID_12858',
            'ent1': None,
            'ent2': None}
    """

    # initialize node types node type (cls=ontology class, ent1/ent2=instance or subclass node)
    nodes = {'cls1': None, 'cls2': None, 'ent1': None, 'ent2': None}

    if edge_info['n1'] == 'class' and edge_info['n2'] == 'class':
        nodes['cls1'] = edge_info['uri'][0] + edge_info['edges'][0]
        nodes['cls2'] = edge_info['uri'][1] + edge_info['edges'][1]
    elif edge_info['n1'] == 'class' and edge_info['n2'] != 'class':
        nodes['cls1'] = edge_info['uri'][0] + edge_info['edges'][0]
        nodes['ent1'] = edge_info['uri'][1] + edge_info['edges'][1]
    elif edge_info['n1'] != 'class' and edge_info['n2'] == 'class':
        nodes['ent1'] = edge_info['uri'][0] + edge_info['edges'][0]
        nodes['cls1'] = edge_info['uri'][1] + edge_info['edges'][1]
    else:
        nodes['ent1'] = edge_info['uri'][0] + edge_info['edges'][0]
        nodes['ent2'] = edge_info['uri'][1] + edge_info['edges'][1]

    return nodes


def maps_node_ids_to_integers(graph: Graph, write_location: str, output_ints: str, output_ints_map: str) -> None:
    """Loops over the knowledge graph in order to create three different types of files:
        - Integers: a tab-delimited `.txt` file containing three columns, one for each part of a triple (i.e.
        subject, predicate, object). The subject, predicate, and object identifiers have been mapped to integers.
        - Identifiers: a tab-delimited `.txt` file containing three columns, one for each part of a triple (i.e.
        subject, predicate, object). Both the subject and object identifiers have not been mapped to integers.
        - Identifier-Integer Map: a `.json` file containing a dictionary where the keys are node identifiers and
        the values are integers.

    Args:
        graph: An rdflib graph object.
        write_location: A string pointing to a local directory for writing data.
        output_ints: the name and file path to write out results.
        output_ints_map: the name and file path to write out results.

    Returns:
        None.

    Raises:
        ValueError: If the length of the graph is not the same as the number of extracted triples.
    """

    # create dictionary for mapping and list to write edges to
    node_map, output_triples, node_counter = {}, 0, 0  # type: ignore
    graph_len = len(graph)

    # build graph from input file and set counter
    out_ints = open(write_location + output_ints, 'w')
    out_ids = open(write_location + '_'.join(output_ints.split('_')[:-1]) + '_Identifiers.txt', 'w')

    # write file headers
    out_ints.write('subject' + '\t' + 'predicate' + '\t' + 'object' + '\n')
    out_ids.write('subject' + '\t' + 'predicate' + '\t' + 'object' + '\n')

    for edge in tqdm(graph):
        if str(edge[0]) not in node_map:
            node_counter += 1
            node_map[str(edge[0])] = node_counter
        if str(edge[1]) not in node_map:
            node_counter += 1
            node_map[str(edge[1])] = node_counter
        if str(edge[2]) not in node_map:
            node_counter += 1
            node_map[str(edge[2])] = node_counter

        # convert edge labels to ints
        subj, pred, obj = str(edge[0]), str(edge[1]), str(edge[2])
        out_ints.write('%d' % node_map[subj] + '\t' + '%d' % node_map[pred] + '\t' + '%d' % node_map[obj] + '\n')
        out_ids.write(subj + '\t' + pred + '\t' + obj + '\n')

        # update counter and delete edge
        output_triples += 1
        graph.remove(edge)

    out_ints.close(), out_ids.close()

    # CHECK - verify we get the number of edges that we would expect to get
    if graph_len != output_triples:
        raise ValueError('ERROR: The number of triples is incorrect!')
    else:
        with open(write_location + '/' + output_ints_map, 'w') as file_name:
            json.dump(node_map, file_name)

    # clean up environment
    del graph

    return None


def converts_rdflib_to_networkx(write_location: str, full_kg: str, graph: Optional[Graph] = None) -> None:
    """Converts an RDFLib.Graph object into a Networkx MultiDiGraph and pickles a copy locally.

    Args:
        write_location: A string pointing to a local directory for writing data.
        full_kg: A string containing the subdirectory and name of the the knowledge graph file.
        graph: An rdflib graph object.

    Returns:
        None.

    Raises:
        IOError: If the file referenced by filename does not exist.
    """

    print('\nConverting Knowledge Graph to MultiDiGraph')

    # read in knowledge graph if class graph attribute is not present
    if not graph or len(graph) == 0:
        graph = Graph()
        graph.parse(write_location + full_kg)

    # convert graph to networkx object
    nx_mdg = networkx.MultiDiGraph()

    for s, p, o in tqdm(graph):
        graph.remove((s, p, o))
        nx_mdg.add_edge(s, o, **{'key': p})

    # pickle networkx graph
    print('\nPickling MultiDiGraph. For Large Networks Process Takes Several Minutes.')
    networkx.write_gpickle(nx_mdg, write_location + full_kg[:-4] + '_Networkx_MultiDiGraph.gpickle')

    # clean up environment
    del graph, nx_mdg

    return None
