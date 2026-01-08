# Copyright: (c) 2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import logging
from string import Template
from typing import Generator, List, Optional, Set

from SPARQLWrapper import DIGEST, JSON, POST, QueryResult, SPARQLWrapper, BASIC
from rdflib import RDF, Graph, URIRef
from rdflib.query import Result

from . import COY, GN


logger = logging.getLogger(__name__)


class GraphConsistencyKeeper:
    """
    FIXME: too CoyPu specific

    Idea: Write cleanup step functions that can be registered for
    inserts/updates/delete operations on resource of specific type (Python
    class or RDF type)
    """
    def __init__(
            self,
            sparql_endpoint: str,
            subgraph_name: str,
            sparql_endpoint_user: Optional[str],
            sparql_endpoint_pw: Optional[str],
            sparql_endpoint_auth_type: str
    ):
        self.subgraph_name: str = subgraph_name

        self.potential_from_clause: str = \
            f'FROM <{self.subgraph_name}>' if self.subgraph_name else ''

        self.potential_with_clause: str = \
            f'WITH <{self.subgraph_name}>' if self.subgraph_name else ''

        self.sparql_endpoint: SPARQLWrapper = SPARQLWrapper(sparql_endpoint)
        self.sparql_endpoint.setMethod(POST)
        self.sparql_endpoint.setReturnFormat(JSON)

        if sparql_endpoint_user and sparql_endpoint_pw:
            if sparql_endpoint_auth_type == 'digest':
                self.sparql_endpoint.setHTTPAuth(DIGEST)
            elif sparql_endpoint_auth_type == 'basic':
                self.sparql_endpoint.setHTTPAuth(BASIC)
            else:
                raise ValueError('Auth type must be either \'digest\' or \'basic\'')

            self.sparql_endpoint.setCredentials(sparql_endpoint_user, sparql_endpoint_pw)
            
        elif sparql_endpoint_user or sparql_endpoint_pw:
            # only one is defined
            raise Exception("Dataset SPARQL endpoint credentials incomplete.")
        
        self.already_deleted_articles: Set[URIRef] = set()
        self.already_deleted_topics: Set[URIRef] = set()
        self.already_deleted_news_summaries: Set[URIRef] = set()
        self.already_deleted_news_sources: Set[URIRef] = set()
        self.already_deleted_osm_elements: Set[URIRef] = set()
        self.already_deleted_labeled_resources: Set[URIRef] = set()
    
    def __query(self, query_str: str) -> Optional[QueryResult]:
        self.sparql_endpoint.setQuery(query_str)

        for t in range(1, 3):
            try:
                return self.sparql_endpoint.query()

            except Exception as e:
                logger.error(
                    f'graphConsistencyKeeper.py query try #{t} failed with '
                    f'following exception: {e}'
                )

                if t == 2:
                    raise e

    def __query_and_convert(self, query_str: str) -> QueryResult.ConvertResult:
        return self.__query(query_str).convert()

    def __query_associated_articles(self, resource_uri:URIRef) -> List[URIRef]:
        query_str: str = Template("""
PREFIX gn: <https://www.geonames.org/ontology#>

SELECT DISTINCT ?a ${subgraph} WHERE {
    ${uri} gn:wikipediaArticle ?a.

}""").substitute(
            subgraph=self.potential_from_clause, 
            uri=resource_uri.n3()
        )
        
        query_result: QueryResult.ConvertResult = self.__query_and_convert(query_str)

        bindings = query_result['results']['bindings']
        article_uris = []
        for binding in bindings:
            article_uri = URIRef(binding['a']['value'])
            article_uris.append(article_uri)
        
        return article_uris

    def __query_mentioned_articles(self, news_summary_uri: URIRef) -> List[URIRef]:
        query_str: str = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>

SELECT DISTINCT ?a ${subgraph} WHERE {
    ${uri} a coy:NewsSummary;
        coy:isIdentifiedBy ?c.
    
    ?c  a nif:Context;
        nif:subString/nif:subString/gn:wikipediaArticle ?a.

}""").substitute(
            subgraph=self.potential_from_clause, 
            uri=news_summary_uri.n3()
        )
        
        query_results: QueryResult.ConvertResult = self.__query_and_convert(query_str)

        bindings = query_results['results']['bindings']
        article_uris = []

        for bind in bindings:
            uri_str = bind['a']['value']
            article_uris.append(URIRef(uri_str))
        
        return article_uris

    def delete_article_and_location_triples(self, article_uri: URIRef):
        # skip if already deleted
        if article_uri in self.already_deleted_articles:
            return

        query_str: str = Template("""
PREFIX coy: <https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX schema: <https://schema.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>

$subgraph
DELETE {

    ${uri} a gn:WikipediaArticle;
        dcterms:source ?doc;
        rdfs:label ?l;
        coy:hasRawHtml ?html;
        schema:name ?name;
        schema:headline ?hl;
        schema:datePublished ?dp;
        schema:dateModified ?dm;
        owl:sameAs ?wd;
        coy:hasOsmElement ?osm.
    
    ?doc a foaf:Document.

    ?wd ?wd_prop ?wd_obj.

    ?loc a coy:Location;
        gn:wikipediaArticle ${uri};
        rdfs:label ?loc_label;
        owl:sameAs ?wd;
        coy:isIdentifiedBy ?loc_id;
        coy:isLocatedIn ?parent_loc;
        coy:hasLatitude ?lat;
        coy:hasLongitude ?long;
        coy:hasLocation ?point.

} WHERE {

    # Article entity
    ${uri} a gn:WikipediaArticle;
        dcterms:source ?doc;
        rdfs:label ?l.
        
    OPTIONAL{$uri coy:hasRawHtml ?html.}
    OPTIONAL{$uri coy:hasOsmElement ?osm. }
    OPTIONAL{$uri schema:name ?name.}
    OPTIONAL{$uri schema:headline ?hl.}
    OPTIONAL{$uri schema:datePublished ?dp.}
    OPTIONAL{$uri schema:dateModified ?dm.}
    OPTIONAL{
        $uri owl:sameAs ?wd. 
        
        # one-hop graph
        ?wd ?wd_prop ?wd_obj.
    }

    ?doc a foaf:Document.

    # Location entity
    OPTIONAL{
        ?loc a coy:Location;
            gn:wikipediaArticle ${uri};
            rdfs:label ?loc_label.
        
        OPTIONAL{?loc owl:sameAs ?wd.}
        OPTIONAL{?loc coy:isIdentifiedBy ?loc_id.}
        OPTIONAL{?loc coy:isLocatedIn ?parent_loc.}

        # Coordinates
        OPTIONAL{
            ?loc coy:hasLatitude ?lat;
                coy:hasLongitude ?long;
                coy:hasLocation ?point. 
        }
    }
}""").substitute(
            subgraph=self.potential_with_clause, 
            uri=article_uri.n3())

        self.__query(query_str)

        # track as already deleted
        self.already_deleted_articles.add(article_uri)

    def delete_topic_triples(self, topic_uri: URIRef):
        # skip if already deleted
        if topic_uri in self.already_deleted_topics:
            return

        # if it's an ArticleTopic:
        # query article of topic before deleting
        article_uris = self.__query_associated_articles(topic_uri)

        # delete articles (should only be one)
        for article_uri in article_uris:
            self.delete_article_and_location_triples(article_uri)
        
        ## delete topic triples
        query_str: str = Template("""
PREFIX coy: <https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>

${subgraph}
DELETE {

    $uri a coy:TextTopic;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasMentionDate ?md;
        coy:isOccuringDuring ?pt;
        coy:hasRawHtml ?html;
        
        a coy:ArticleTopic;
        gn:wikipediaArticle ?a;
        coy:hasLocation ?loc;
        coy:hasTimespan ?ts.


} WHERE {

    $uri a coy:TextTopic;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasMentionDate ?md.
    OPTIONAL{$uri coy:isOccuringDuring ?pt.}
    OPTIONAL{$uri coy:hasRawHtml ?html.}

    # if its an ArticleTopic
    OPTIONAL{
        $uri a coy:ArticleTopic;
            gn:wikipediaArticle ?a;
            coy:hasLocation ?loc.
        OPTIONAL{ $uri coy:hasTimespan ?ts }
    }

}""").substitute(
            subgraph=self.potential_with_clause, 
            uri=topic_uri.n3()
        )
        
        self.__query(query_str)

        # track as already deleted
        self.already_deleted_topics.add(topic_uri)

    def delete_news_summary_triples(self, news_summary_uri: URIRef):
        # skip if already deleted
        if news_summary_uri in self.already_deleted_news_summaries:
            return
        
        query_str: str = Template("""
PREFIX coy: <https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>

${subgraph}
DELETE {

    $uri a coy:NewsSummary;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasTag ?tag;
        coy:hasMentionDate ?date;
        coy:hasRawHtml ?html;
        coy:isIdentifiedBy ?c;
        coy:hasWikidataEventType ?ev_type;
        coy:isOccuringDuring ?pt.
        
    ?c a nif:Context;
        rdfs:label ?c_l;
        nif:sourceUrl ?wiki_source;
        dcterms:source ?news_source;
        nif:isString ?c_str;
        nif:beginIndex ?c_bi;
        nif:endIndex ?c_ei;
        nif:subString ?s.
    
    ?s a nif:Sentence;
        nif:referenceContext ?c;
        nif:beginIndex ?s_bi;
        nif:endIndex ?s_ei;
        nif:anchorOf ?s_anchor;
        rdfs:label ?s_l;
        nif:nextSentence ?s_next;
        nif:previousSentence ?s_prev;
        nif:subString ?link. 

    ?link a nif:Phrase;
        nif:referenceContext ?s;
        nif:beginIndex ?link_bi;
        nif:endIndex ?link_ei;
        nif:anchorOf ?link_anchor;
        rdfs:label ?link_l;
        gn:wikipediaArticle ?a.

} WHERE {

    $uri a coy:NewsSummary;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasMentionDate ?date;
        coy:hasRawHtml ?html;
        coy:isIdentifiedBy ?c.
    OPTIONAL{$uri coy:hasTag ?tag.}
    OPTIONAL{$uri coy:hasWikidataEventType ?ev_type.}
    OPTIONAL{$uri coy:isOccuringDuring ?pt.}

    ?c a nif:Context;
        rdfs:label ?c_l;
        nif:sourceUrl ?wiki_source;
        nif:isString ?c_str;
        nif:beginIndex ?c_bi;
        nif:endIndex ?c_ei;
        nif:subString ?s.
    OPTIONAL{?c dcterms:source ?news_source.}
    
    ?s a nif:Sentence;
        nif:referenceContext ?c;
        nif:beginIndex ?s_bi;
        nif:endIndex ?s_ei;
        nif:anchorOf ?s_anchor;
        rdfs:label ?s_l.
    OPTIONAL{ ?s nif:nextSentence ?s_next. }
    OPTIONAL{ ?s nif:previousSentence ?s_prev. }
    
    OPTIONAL{ 
        ?s nif:subString ?link. 

        ?link a nif:Phrase;
            nif:referenceContext ?s;
            nif:beginIndex ?link_bi;
            nif:endIndex ?link_ei;
            nif:anchorOf ?link_anchor;
            rdfs:label ?link_l;
            gn:wikipediaArticle ?a.
    }
    
}""").substitute(
            subgraph=self.potential_with_clause, 
            uri=news_summary_uri.n3())

        self.__query(query_str)

        # track as already deleted
        self.already_deleted_news_summaries.add(news_summary_uri)

    def delete_news_source_triples(self, news_source_uri: URIRef):
        # skip if already deleted
        if news_source_uri in self.already_deleted_news_sources:
            return

        query_str: str = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

${subgraph}
DELETE {

    ${uri} a coy:News;
        rdfs:label ?l.

} WHERE {

    ${uri} a coy:News;
        rdfs:label ?l.

}""").substitute(
            subgraph=f'WITH <{self.subgraph_name}>' if self.subgraph_name else '',
            uri=news_source_uri.n3())

        # run DELETE 'query'/operation
        self.__query(query_str)

        # track as already deleted
        self.already_deleted_news_sources.add(news_source_uri)

    def delete_osm_element_triples(self, osm_element_uri: URIRef):
        # skip if already deleted
        if osm_element_uri in self.already_deleted_osm_elements:
            return
        
        query_str: str = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

${subgraph}
DELETE {

    ${uri} a coy:OsmElement;
        rdfs:label ?l;
        coy:hasOsmId ?id;
        coy:hasOsmType ?type;
        geo:asWKT ?wkt.

} WHERE {

    ${uri} a coy:OsmElement;
        rdfs:label ?l.
    OPTIONAL{ $uri coy:hasOsmId ?id }
    OPTIONAL{ $uri coy:hasOsmType ?type }
    OPTIONAL{ $uri geo:asWKT ?wkt }

}""").substitute(
            subgraph=self.potential_with_clause, 
            uri=osm_element_uri.n3())

        # run DELETE 'query'/operation
        self.__query(query_str)

        # track as already deleted
        self.already_deleted_osm_elements.add(osm_element_uri)

    def delete_label_triples(self, uri: URIRef):
        # skip if already deleted
        if uri in self.already_deleted_labeled_resources:
            return

        query_str: str = Template("""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

${subgraph}
DELETE  {
    
    ${uri} rdfs:label ?l.

} WHERE {
    
    ${uri} rdfs:label ?l.

}""").substitute(
            subgraph=self.potential_with_clause, 
            uri=uri.n3())

        # Run DELETE 'query'/operation
        self.__query(query_str)

        # track as already deleted
        self.already_deleted_labeled_resources.add(uri)

    @staticmethod
    def query_wikidata_class_uris_having_a_label(g: Graph) -> Generator:
        query_str: str = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>

SELECT DISTINCT ?c WHERE {
    ?wd_e wdt:P31 ?c.
    ?c rdfs:label ?l.
}"""

        query_results: Result = g.query(query_str)
        for row in query_results:
            yield URIRef(row.c)

    def delete_old_triples_in_endpoint(self, new_graph: Graph):
        article_uris = new_graph.subjects(RDF.type, GN.WikipediaArticle, unique=True)
        for article_uri in article_uris:
            assert isinstance(article_uri, URIRef)
            self.delete_article_and_location_triples(article_uri)
    
        news_summary_uris = new_graph.subjects(RDF.type, COY.NewsSummary, unique=True)
        for news_summary_uri in news_summary_uris:
            assert isinstance(news_summary_uri, URIRef)
            self.delete_news_summary_triples(news_summary_uri)
        
        topic_uris = new_graph.subjects(RDF.type, COY.TextTopic, unique=True)
        for topic_uri in topic_uris:
            assert isinstance(topic_uri, URIRef)
            self.delete_topic_triples(topic_uri)
    
        osm_element_uris = new_graph.subjects(RDF.type, COY.OsmElement, unique=True)
        for osm_element_uri in osm_element_uris:
            assert isinstance(osm_element_uri, URIRef)
            self.delete_osm_element_triples(osm_element_uri)
    
        wikidata_class_uris = self.query_wikidata_class_uris_having_a_label(new_graph)
        for wikidata_class_uri in wikidata_class_uris:
            self.delete_label_triples(wikidata_class_uri)
    

if __name__ == '__main__':
    import argparse
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '-i', '--input',
        action='store', 
        help='The path of the base graph module file.',
        required=True
    )

    parser.add_argument(
        '-de', '--dataset_endpoint',
        action='store',
        help='Sets the sparql endpoint URL of the dataset from which data '
             'will be removed if the parent entities also exist in the graph.',
        required=False
    )

    parser.add_argument(
        '-des', '--dataset_endpoint_subgraph',
        action='store',
        help='The subgraph used for the dataset.'
    )

    parser.add_argument(
        '-deu', '--dataset_endpoint_username',
        action='store',
        help='The username used for the dataset sparql endpoint.'
    )

    parser.add_argument(
        '-dep', '--dataset_endpoint_pw',
        action='store',
        help='The password used for the dataset sparql endpoint.'
    )

    parser.add_argument(
        '-deat', '--dataset_endpoint_auth_type',
        action='store',
        help='The auth type used for the dataset sparql endpoint.',
        type=str,
        choices=['basic', 'digest'],
        default='basic'
    )
    
    args = parser.parse_args()
    
    graph_consistency_keeper = GraphConsistencyKeeper(
        args.dataset_endpoint, 
        args.dataset_endpoint_subgraph, 
        args.dataset_endpoint_username, 
        args.dataset_endpoint_pw,
        args.dataset_endpoint_auth_type,
    )

    # load all graph modules
    graph_new = Graph()
    base_path, base_filename = os.path.split(os.path.abspath(args.input))

    for graph_module_name in ['base', 'raw', 'osm', 'ohg']:
        filename = base_filename.replace('base', graph_module_name)
        graph_new.parse(Path(base_path) / filename)

    # delete old versions extracted data from the endpoint, where a new version exists in the file
    graph_consistency_keeper.delete_old_triples_in_endpoint(graph_new)
