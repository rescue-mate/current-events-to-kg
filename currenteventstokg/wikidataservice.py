# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import logging
from atexit import register
from json import dump, load
from os import makedirs
from os.path import exists
from pathlib import Path
from string import Template
import time
from typing import Dict, List, Tuple, Set
from urllib.error import HTTPError

from rdflib import BNode, Graph, Literal, URIRef
from SPARQLWrapper import JSON, SPARQLWrapper, __version__, QueryResult

from .sleeper import Sleeper


logger = logging.getLogger(__name__)


class WikidataService(Sleeper):
    # Limits: https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#Query_limits

    def __init__(
            self,
            basedir: Path,
            cache_dir: Path,
            program_name: str,
            program_version: str,
            program_git_repo: str,
            server_address: str,
            min_seconds_between_queries: int = 5
    ):
        super().__init__()
        self.basedir: Path = basedir

        self.min_seconds_between_queries = min_seconds_between_queries

        self.one_hop_cache_dir: Path = self.basedir / cache_dir / 'wikidata_one_hop/'
        makedirs(self.one_hop_cache_dir, exist_ok=True)

        self.osm_cache_file_path: Path = self.basedir / cache_dir / 'osm_entity_cache.json'
        self.__load_osm_cache()

        self.higher_level_location_cache_file_path: Path = \
            self.basedir / cache_dir / 'higher_level_location_cache.json'

        self.__load_higher_level_location_cache()

        self.label_cache_file_path: Path = self.basedir / cache_dir / 'label_cache.json'
        self.__load_label_cache()

        self.wikidata_to_wikipedia_cache_path: Path = \
            self.basedir / cache_dir / 'wd_to_wp_cache.json'
        self.__load_wikidata_to_wikipedia_cache()
        
        # save caches after termination
        register(self.__save_caches)

        # wikidata wants a "bot" included in agent string
        user_agent_identifier = \
                program_name + '(bot)/' + program_version + \
                ' (' + program_git_repo + ') ' + f'sparqlwrapper {__version__}'

        logger.info(f'wikidata server: {server_address}')
        logger.info(f'wikidata user-agent: {user_agent_identifier}')

        self.sparql_endpoint = SPARQLWrapper(server_address, agent=user_agent_identifier)
    

    def get_entity_labels(self, entity_uri_strings: List[str]) -> Dict[str,str]:
        result = {}
        run_entity_id_query: bool = False
        is_first: bool = True

        query_str = '''PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?e ?l WHERE{
'''

        for entity_uri_str in entity_uri_strings:
            entity_id = entity_uri_str.split('/')[-1]

            if entity_id in self.label_cache:
                result[entity_id] = self.label_cache[entity_id]

            else:
                run_entity_id_query = True
                if is_first:
                    is_first = False
                    query_str += Template('''{
    BIND(wd:$e AS ?e).
    ?e rdfs:label ?l.
}''').substitute(e=entity_id)

                else:  # is not first entity
                    query_str += Template('''UNION {
    BIND(wd:$e AS ?e).
    ?e rdfs:label ?l.
}''').substitute(e=entity_id)
        
        if run_entity_id_query:
            query_str += '\nFILTER(LANG(?l) = "en") .\n}'
            
            res = self.__query_and_convert_three_tries(query_str)

            for row in res['results']['bindings']:
                entity_id = row['e']['value'].split('/')[-1]
                label = row['l']['value']

                result[entity_id] = label
                self.label_cache[entity_id] = label

        return result        

    def get_higher_level_locations(self, entity_uri_str: str) -> Dict[str, List[str]]:
        entity_id = entity_uri_str.split('/')[-1]

        if entity_id in self.higher_level_location_cache:
            result = self.higher_level_location_cache[entity_id]

        else:
            # exclude prop for pictures about places with filter
            query_str = Template('''
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT DISTINCT ?wd_r ?loc WHERE{
  wd:$e ?wdt_r ?loc .
  
  ?wd_r wdt:P1647+ wd:P276. # transitive subprop of location
  ?wd_r wikibase:directClaim ?wdt_r .
  FILTER NOT EXISTS{ ?wd_r wdt:P1647 wd:P18. } 
}''').substitute(e=entity_id)

            res = self.__query_and_convert_three_tries(query_str)

            result = {}
            for row in res['results']['bindings']:
                value = row['loc']['value']
                if value in result:
                    result[value].append(row['wd_r']['value'])
                else:
                    result[value] = [ row['wd_r']['value'] ]

            self.higher_level_location_cache[entity_id] = result

        return result

    def get_one_hop_subgraph(self, entity_uri_str: str) -> Graph:
        file_path = self.__get_one_hop_subgraph_cache_file_name(entity_uri_str)

        if exists(file_path):
            one_hop_subgraph: Graph = self.__load_one_hop_subgraph(entity_uri_str)

        else:
            # use SELECT query to get all triples 
            # (because CONSTRUCT is not supported from our wikidata server)

            query_str = Template('''
SELECT ?p ?o WHERE {
    <$e> ?p ?o .
}''').substitute(e=entity_uri_str)

            json = self.__query_and_convert_three_tries(query_str)

            one_hop_subgraph = Graph()
            for row in json['results']['bindings']:
                p, o = row['p'], row['o']

                # create predicate object
                assert p['type'] == 'uri'
                predicate = URIRef(p['value'])

                # create object object
                if o['type'] == 'uri':
                    obj = URIRef(o['value'])

                elif o['type'] == 'literal':
                    lang = None
                    if 'xml:lang' in o:
                        lang = o['xml:lang']

                    dtype = None
                    if 'datatype' in o:
                        dtype = o['datatype']
                    
                    obj = Literal(o['value'], datatype=dtype, lang=lang)

                elif o['type'] == 'bnode':
                    # cut "_:" from front of value
                    obj = BNode(value=o['value'][2:])

                else:
                    raise ValueError(o['type'] + str(o))
                
                # add triple
                one_hop_subgraph.add((URIRef(entity_uri_str), predicate, obj))

            self.__cache_one_hop_subgraph(entity_uri_str, one_hop_subgraph)
            
        return one_hop_subgraph

    def get_osm_entities(self, entity_uri: str) -> Tuple[List[str], List[str]]:
        # osmrelids: e.g. 62422  -> https://www.wikidata.org/wiki/Property:P402
        # osmobjs: [way|node]/{id} -> https://www.wikidata.org/wiki/Property:P10689

        def is_valid_osm_object(x: str):
            a, b = x.split('/', 1)

            if a in ['way', 'node'] and b.isdecimal():
                return True
            return False
        
        def is_valid_osm_relation(x: str):
            if x.isdecimal():
                return True
            return False

        if entity_uri in self.osm_cache:
            res = self.osm_cache[entity_uri]

            osm_rel_ids = res["osmrelids"]
            osm_objs = res["osmobjs"]

        else:
            query_str = Template("""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?osmrelid ?osmobj WHERE {
    OPTIONAL {<$e> wdt:P402 ?osmrelid . }
    OPTIONAL {<$e> wdt:P10689 ?osmobj. }
}""").substitute(e=entity_uri)
            
            results = self.__query_and_convert_three_tries(query_str)

            osm_rel_ids_set: Set[str] = set()
            osm_objs_set: Set[str] = set()
            for row in results['results']['bindings']:
                if 'osmrelid' in row:
                    value = row['osmrelid']['value']

                    if is_valid_osm_relation(value):
                        osm_rel_ids_set.add(value)

                if 'osmobj' in row:
                    value = row['osmobj']['value']

                    if is_valid_osm_object(value):
                        osm_objs_set.add(value)
            
            osm_objs = list(osm_objs_set)
            osm_rel_ids = list(osm_rel_ids_set)
            self.osm_cache[entity_uri] = {"osmrelids": osm_rel_ids, "osmobjs": osm_objs}
            
        return osm_rel_ids, osm_objs

    def get_wikipedia_article_urls(self, entity_uri_strings: List[str]) -> Dict[str, str]:
        result = {}

        for entity_uri_str in entity_uri_strings:
            entity_id = entity_uri_str.rsplit('/',1)[-1]

            if entity_id in self.wikidata_to_wikipedia_cache:
                wikipedia_id = self.wikidata_to_wikipedia_cache[entity_id]

                if wikipedia_id is not None:
                    result[entity_id] = wikipedia_id

            else:
                query_str = Template("""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
SELECT DISTINCT ?a WHERE{
    ?a  schema:about wd:$e;
	    schema:isPartOf <https://en.wikipedia.org/>.
}""").substitute(e=entity_id)
                
                res = self.__query_and_convert_three_tries(query_str)

                if len(res['results']['bindings']) > 0:
                    for row in res['results']['bindings']:
                        article_url = row['a']['value']

                        result[entity_id] = article_url
                        self.wikidata_to_wikipedia_cache[entity_id] = article_url

                else:
                    # no article exist for this wd entity
                    self.wikidata_to_wikipedia_cache[entity_id] = None

        return result        

    def __query_and_convert_three_tries(self, query: str) -> QueryResult.ConvertResult:
        self.sparql_endpoint.setQuery(query)
        self.sparql_endpoint.setReturnFormat(JSON)

        self.sleep_until_new_request_allowed(self.min_seconds_between_queries)

        for t in range(3):
            try:
                res = self.sparql_endpoint.queryAndConvert()

                return res

            except Exception as e:
                if isinstance(e, HTTPError) and e.code == 429:
                    # check when query can be repeated (untested, never happened)
                    timeout = int(e.headers['Retry-After'])

                    logger.warning(f'Wikidata request limit exceeded! Waiting {timeout} sec...')
                    time.sleep(timeout)

                else:
                    logger.error('\nwikidataservice.py query try #' + str(t+1))
                    logger.error(e)
                    if t == 2:
                        raise e

    def __load_osm_cache(self):
        if exists(self.osm_cache_file_path):
            with open(self.osm_cache_file_path, mode='r', encoding='utf-8') as f:
                self.osm_cache = load(f)

        else:
            self.osm_cache = {}

    def __load_higher_level_location_cache(self):
        if exists(self.higher_level_location_cache_file_path):
            with open(self.higher_level_location_cache_file_path, mode='r', encoding='utf-8') as f:
                self.higher_level_location_cache = load(f)

        else:
            self.higher_level_location_cache = {}

    def __load_label_cache(self):
        if exists(self.label_cache_file_path):
            with open(self.label_cache_file_path, mode='r', encoding='utf-8') as f:
                self.label_cache = load(f)

        else:
            self.label_cache = {}

    def __load_wikidata_to_wikipedia_cache(self):
        if exists(self.wikidata_to_wikipedia_cache_path):
            with open(self.wikidata_to_wikipedia_cache_path, mode='r', encoding='utf-8') as f:
                self.wikidata_to_wikipedia_cache = load(f)

        else:
            self.wikidata_to_wikipedia_cache = {}

    def __save_caches(self):
        with open(self.osm_cache_file_path, mode='w', encoding='utf-8') as f:
            dump(self.osm_cache, f)
        
        with open(self.higher_level_location_cache_file_path, mode='w', encoding='utf-8') as f:
            dump(self.higher_level_location_cache, f)

        with open(self.label_cache_file_path, mode='w', encoding='utf-8') as f:
            dump(self.label_cache, f)
        
        with open(self.wikidata_to_wikipedia_cache_path, mode='w', encoding='utf-8') as f:
            dump(self.wikidata_to_wikipedia_cache, f)
    
    def __get_one_hop_subgraph_cache_file_name(self, entity_uri_str: str):
        entity_id = entity_uri_str.split("/")[-1]

        return self.one_hop_cache_dir / (entity_id + ".jsonld")

    def __cache_one_hop_subgraph(self, entity_uri_str: str, graph: Graph):
        file_path = self.__get_one_hop_subgraph_cache_file_name(entity_uri_str)

        s = graph.serialize(format="json-ld")
        with open(file_path, mode='w', encoding="utf-8") as f:
            f.write(s)

    def __load_one_hop_subgraph(self, entity_uri: str) -> Graph:
        file_path = self.__get_one_hop_subgraph_cache_file_name(entity_uri)
        
        g = Graph()
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                g.parse(file=f)

        except Exception as e:
            logger.error(f'Could not load {file_path} ({e})...')
                
        return g
