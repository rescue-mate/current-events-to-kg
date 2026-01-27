# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import datetime
import logging
from os import makedirs
from os.path import exists
from pathlib import Path
from typing import overload, Tuple, Optional, List, Dict, Union
from urllib.parse import quote_plus

from rdflib import FOAF, OWL, RDF, RDFS, XSD, Graph, Literal, URIRef

from . import (COY, WGS, GEO, WD, GN, SCHEMA, DCTERMS,
               events_ns, article_topics_ns, text_topics_ns, contexts_ns,
               sentences_ns, phrases_ns, locations_ns, osm_element_ns, point_ns,
               timespan_ns, wikipedia_article_ns)
from .graphconsistencykeeper import GraphConsistencyKeeper
from .model.article import Article
from .model.event import Event
from .model.infoboxRow import InfoboxRowDate, InfoboxRowTime, InfoboxLocationRow
from .model.osmElement import OSMElement
from .model.topic import Topic

logger = logging.getLogger(__name__)


class OutputRdf:
    def __init__(
            self,
            basedir: Path,
            dataset_endpoint: str,
            dataset_endpoint_subgraph: str,
            dataset_endpoint_username: str,
            dataset_endpoint_pw: str,
            dataset_endpoint_auth_type: str,
            delete_old_entities: bool,
            output_folder: Path = Path('./dataset/')
    ):
        self.basedir: Path = basedir

        self.outputFolder: Path = self.basedir / output_folder
        makedirs(self.outputFolder, exist_ok=True)

        self.graphs: Dict[str, Graph] = {
            # FIXME: explain
            'base': Graph(),
            # FIXME: explain
            'raw': Graph(),
            # FIXME: explain
            'ohg': Graph(),
            # FIXME: explain
            'osm': Graph(),
        }

        self.graph_consistency_keeper = GraphConsistencyKeeper(
            sparql_endpoint=dataset_endpoint,
            subgraph_name=dataset_endpoint_subgraph,
            sparql_endpoint_user=dataset_endpoint_username,
            sparql_endpoint_pw=dataset_endpoint_pw,
            sparql_endpoint_auth_type=dataset_endpoint_auth_type,
        )

        self.delete_old_entities: bool = delete_old_entities

    @staticmethod
    def __get_osm_uri(osm_element: OSMElement) -> URIRef:
        suffix = f'{osm_element.osm_type}_{osm_element.osm_id}'
        uri = osm_element_ns[suffix]

        return uri

    @staticmethod
    def __get_point_uri(coordinates: List[float]) -> URIRef:
        url_encoded_coordinates = quote_plus(f'{coordinates[0]}_{coordinates[1]}')
        uri = point_ns[url_encoded_coordinates]

        return uri

    @staticmethod
    def __get_event_id(event: Event) -> str:
        date_ = event.date_

        return f'{date_.year:04}-{date_.month:02}-{date_.day:02}_{event.event_index}'

    @staticmethod
    def __get_wiki_article_url_identifier(article: Article) -> str:
        return article.url.rsplit('/', 1)[-1]

    @overload
    def __get_event_uri(self, topic: Topic) -> URIRef:
        pass

    @overload
    def __get_event_uri(self, event: Event) -> URIRef:
        pass

    def __get_event_uri(self, obj: Union[Topic, Event]) -> URIRef:
        if isinstance(obj, Event):
            suffix = self.__get_event_id(obj)
            uri = events_ns[suffix]

        elif isinstance(obj, Topic):
            if obj.article:
                # Topics with link to wiki article
                suffix = self.__get_wiki_article_url_identifier(obj.article)
                uri = article_topics_ns[suffix]

            else:
                # Topics without link
                suffix = quote_plus(obj.text)
                uri = text_topics_ns[suffix]

        else:
            raise RuntimeError(f'Unhandled type ({type(obj)}) in __get_event_uri')
                
        return uri

    def __get_place_uri(self, article: Article) -> URIRef:
        suffix = self.__get_wiki_article_url_identifier(article)
        uri = locations_ns[suffix]

        return uri

    def __get_context_uri(self, event: Event) -> URIRef:
        suffix = self.__get_event_id(event)
        uri = contexts_ns[suffix]

        return uri

    @staticmethod
    def __get_sentence_uri(context_uri: URIRef, index: int) -> URIRef:
        local_part: str = context_uri.rsplit('/', 1)[-1] + f'_{index}'
        uri = sentences_ns[local_part]

        return uri

    @staticmethod
    def __get_phrase_uri(sentence_uri: URIRef, index: int) -> URIRef:
        local_part: str = sentence_uri.rsplit('/', 1)[-1] + f'_{index}'
        uri = phrases_ns[local_part]

        return uri

    def __get_article_uri(self, article: Article) -> URIRef:
        suffix: str = self.__get_wiki_article_url_identifier(article)
        uri: URIRef = wikipedia_article_ns[suffix]

        return uri

    @staticmethod
    def __get_timespan_uri(
            date_or_beginning: Optional[datetime.datetime],
            ending: Optional[datetime.datetime],
            ongoing: bool,
            time: Optional[datetime.time],
            end_time: Optional[datetime.time],
            timezone: Optional[str]
    ):
        parts = []
        if date_or_beginning is not None:
            # FIXME: In [15]: print(f'{datetime(2023, 1, 16)}')  # introduces whitespaces
            # 2023-01-16 00:00:00
            parts.append(f'sd_{date_or_beginning}')

        if ending is not None:
            # FIXME: Introduces whitespaces
            parts.append(f'ed_{ending}')

        elif ongoing:
            parts.append('o')

        if time is not None:
            parts.append(f'st_{time}')

        if end_time is not None:
            parts.append(f'et_{end_time}')

        if timezone:
            parts.append(f't_{timezone}')

        suffix = quote_plus('_'.join(parts))
        uri = timespan_ns[suffix]

        return uri
    
    def __add_coordinates(
            self,
            graph: Graph,
            geo_feature_uri: URIRef,
            coordinates: list[float]
    ):
        # add coordinates via wgs:Point
        point_uri: URIRef = self.__get_point_uri(coordinates)
        graph.add((geo_feature_uri, GEO.hasGeometry, point_uri))
        graph.add((point_uri, RDF.type, WGS.Point))

        graph.add((
            point_uri,
            RDFS.label,
            Literal(f'{coordinates[0]},{coordinates[1]}', datatype=XSD.string)
        ))
        
        graph.add((point_uri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((point_uri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))

        # add coords directly for compatibility
        graph.add((
            geo_feature_uri,
            COY.hasLatitude,
            Literal(str(coordinates[0]), datatype=XSD.decimal)
        ))

        graph.add((
            geo_feature_uri,
            COY.hasLongitude,
            Literal(str(coordinates[1]), datatype=XSD.decimal)
        ))

        # TODO: add geo:asWKT
    
    def __add_osm_element(self, target: URIRef, osm_element: OSMElement):
        graph = self.graphs['osm']
        osm_uri = self.__get_osm_uri(osm_element)

        if osm_element.osm_type or osm_element.osm_id or osm_element.wkt:
            graph.add((target, COY.hasOsmElement, osm_uri))
            graph.add((osm_uri, RDF.type, COY.OsmElement))

            graph.add((
                osm_uri,
                RDFS.label,
                Literal(f'{osm_element.osm_type} {osm_element.osm_id}', datatype=XSD.string)
            ))

            if osm_element.osm_type:
                graph.add((
                    osm_uri,
                    COY.hasOsmType,
                    Literal(str(osm_element.osm_type), datatype=XSD.string)
                ))

            if osm_element.osm_id:
                graph.add((
                    osm_uri,
                    COY.hasOsmId,
                    Literal(str(osm_element.osm_id), datatype=XSD.integer)
                ))

            if osm_element.wkt:
                # FIXME: geo:asWKT "..." should be added to geometry, not to spatial feature
                graph.add((
                    osm_uri,
                    GEO.asWKT,
                    Literal(str(osm_element.wkt), datatype=GEO.wktLiteral)
                ))
        
        # delete old triples in dataset endpoint
        if self.delete_old_entities:
            self.graph_consistency_keeper.delete_osm_element_triples(osm_uri)
    
    def __add_place(self, target_graph: Graph, article: Article) -> URIRef:
        place_uri: URIRef = self.__get_place_uri(article)

        # FIXME: Type should be geo:Feature
        target_graph.add((place_uri, RDF.type, COY.Location))

        target_graph.add((
            place_uri,
            RDFS.label,
            Literal(f'{article.name}', datatype=XSD.string)
        ))

        # only use one row as the location (should only be one)
        infobox_location_rows: List[InfoboxLocationRow] = [
            info_box_row
            for info_box_row in article.infobox_rows
            if isinstance(info_box_row, InfoboxLocationRow)
        ]

        infobox_location_row: InfoboxLocationRow = \
            infobox_location_rows[0] if len(infobox_location_rows) > 0 else None

        if infobox_location_row:
            target_graph.add((
                place_uri,
                COY.isIdentifiedBy,
                Literal(str(infobox_location_row.value), datatype=XSD.string)
            ))

            linked_articles: List[Article] = [
                l.article
                for l in infobox_location_row.value_links
                if l.article
            ]

            for location_article in set(infobox_location_row.falcon2_articles + linked_articles):
                article_uri, _ = self.__add_article_triples(location_article)
                location_place_uri: URIRef = self.__add_place(target_graph, location_article)

                target_graph.add((place_uri, COY.isLocatedIn, location_place_uri))
        
        return place_uri

    # FIXME: Method too long
    # FIXME: Many of the data could be expressed with the owl:time vocabulary
    def __add_timespan(self, target_graph: Graph, article: Article) -> Optional[URIRef]:
        # slots
        start_date_slot: Union[datetime.datetime, None] = None
        end_date_slot: Union[datetime.datetime, None] = None
        start_time_slot: Union[datetime.time, None] = None
        end_time_slot: Union[datetime.time, None] = None
        ongoing_flag_slot: bool = False
        timezone_slot: Union[datetime.timezone, None] = None

        timespan_label: str = ''

        # use microformats as date first
        if 'dtstart' in article.microformats.keys():
            start_date_slot = article.microformats['dtstart']
            timespan_label += f'dtstart: {start_date_slot}\n'

        if 'dtend' in article.microformats.keys():
            end_date_slot = article.microformats['dtend']
            timespan_label += f'dtend: {end_date_slot}\n'

        def has_time(dt: datetime.datetime) -> bool:
            t = dt.time()
            if t.hour != 0 and t.minute != 0:
                return True
            else:
                # FIXME: ignores all date-time objects representing times like 00:00:23
                return False

        date_rows: List[InfoboxRowDate] = []
        time_rows: List[InfoboxRowTime] = []

        # infobox_rows: Dict[str, InfoboxRow]
        for row in article.infobox_rows.values():
            if isinstance(row, InfoboxRowTime):
                time_rows.append(row)

            elif isinstance(row, InfoboxRowDate):
                date_rows.append(row)

        # fill slots if empty or more info
        for row in date_rows:
            slot_filled = False

            # fill start
            if row.start_date is not None:
                if start_date_slot is None:
                    start_date_slot = row.start_date
                    slot_filled = True

                # case where just the date is set but no time
                elif start_date_slot is not None and \
                      not has_time(start_date_slot) and \
                      has_time(row.start_date):

                    start_date_slot = start_date_slot.replace(
                        hour=row.start_date.hour,
                        minute=row.start_date.minute
                    )

                    slot_filled = True

            # fill end
            if row.ongoing and end_date_slot is None:
                ongoing_flag_slot = True

            elif row.end_date is not None and not ongoing_flag_slot:
                if end_date_slot is None:
                    end_date_slot = row.end_date
                    slot_filled = True

                # case where just the date is set but no time
                elif end_date_slot is not None and \
                        not has_time(end_date_slot) and \
                        has_time(row.end_date):

                    end_date_slot = end_date_slot.replace(
                        hour=row.end_date.hour,
                        minute=row.end_date.minute
                    )

                    slot_filled = True

            # fill timezone
            if timezone_slot is None:
                if row.start_date is not None and row.start_date.tzinfo is not None:
                    timezone_slot = row.start_date.tzinfo
                    slot_filled = True

                elif row.end_date is not None and row.end_date.tzinfo is not None:
                    timezone_slot = row.end_date.tzinfo
                    slot_filled = True

            if slot_filled:
                timespan_label += f'{row.label}: {row.value}\n'

        for row in time_rows:
            slot_filled = False

            if start_date_slot is not None and end_date_slot is None:
                # combine dates and times to one time span
                # discard time(span) if time(span) produces multiple spans
                if row.start_time is not None and not has_time(start_date_slot):
                    start_date_slot = start_date_slot.replace(
                        hour=row.start_time.hour,
                        minute=row.start_time.minute
                    )

                    slot_filled = True

                if row.end_time is not None:
                    end_date_slot = start_date_slot.replace(
                        hour=row.end_time.hour,
                        minute=row.end_time.minute
                    )

                    slot_filled = True

            elif start_date_slot is None and end_date_slot is None:
                # add time triples extra
                if start_time_slot is None:
                    start_time_slot = row.start_time
                    slot_filled = True

                if end_time_slot is None:
                    end_time_slot = row.end_time
                    slot_filled = True

            if timezone_slot is None:
                if row.start_time.tzinfo is not None:
                    timezone_slot = row.start_time.tzinfo
                    slot_filled = True

                elif row.end_time is not None and row.end_time.tzinfo is not None:
                    timezone_slot = row.end_time.tzinfo
                    slot_filled = True

            if slot_filled:
                timespan_label += f'{row.label}: {row.value}\n'

        # if only the start datetime was found (nothing set the end), assume
        # that the event is a point in time
        if start_date_slot is not None and end_date_slot is None and not ongoing_flag_slot:
            end_date_slot = start_date_slot

        # set the timezone found for all values
        if timezone_slot is not None:
            if start_date_slot is not None:
                start_date_slot = start_date_slot.replace(tzinfo=timezone_slot)

            if end_date_slot is not None:
                end_date_slot = end_date_slot.replace(tzinfo=timezone_slot)

            if start_time_slot is not None:
                start_time_slot = start_time_slot.replace(tzinfo=timezone_slot)

            if end_time_slot is not None:
                end_time_slot = end_time_slot.replace(tzinfo=timezone_slot)

        # store date/time triples from slots
        timespan_uri = None
        if start_date_slot is not None or \
                end_date_slot is not None or \
                ongoing_flag_slot or \
                start_time_slot is not None or \
                end_time_slot is not None:

            timespan_uri = self.__get_timespan_uri(
                date_or_beginning=start_date_slot,
                ending=end_date_slot,
                ongoing=ongoing_flag_slot,
                time=start_time_slot,
                end_time=end_time_slot,
                timezone=timezone_slot
            )

            target_graph.add((timespan_uri, RDF.type, COY.Timespan))

            target_graph.add((
                timespan_uri,
                RDFS.label,
                Literal(timespan_label, datatype=XSD.string)
            ))

            if start_date_slot is not None:
                target_graph.add((
                    timespan_uri,
                    COY.hasStartDate,
                    Literal(start_date_slot.isoformat(), datatype=XSD.dateTime)
                ))

            if end_date_slot is not None:
                target_graph.add((
                    timespan_uri,
                    COY.hasEndDate,
                    Literal(end_date_slot.isoformat(), datatype=XSD.dateTime)
                ))

            elif ongoing_flag_slot:
                target_graph.add((
                    timespan_uri,
                    COY.hasOngoingSpan,
                    Literal('true', datatype=XSD.boolean)
                ))

            if start_time_slot is not None:
                target_graph.add((
                    timespan_uri,
                    COY.hasStartTimestamp,
                    Literal(start_time_slot, datatype=XSD.time)
                ))

            if end_time_slot is not None:
                target_graph.add((
                    timespan_uri,
                    COY.hasEndTimestamp,
                    Literal(end_time_slot, datatype=XSD.time)
                ))

        return timespan_uri

    # FIXME: Method is too long
    def __add_article_triples(
            self,
            article: Article,
            is_topic_article: bool = False
    ) -> Tuple[URIRef, Optional[URIRef]]:

        base_graph: Graph = self.graphs['base']
        raw_graph: Graph = self.graphs['raw']
        one_hop_graphs: Graph = self.graphs['ohg']

        article_uri: URIRef = self.__get_article_uri(article)
    
        base_graph.add((article_uri, RDF.type, GN.WikipediaArticle))

        base_graph.add((
            article_uri,
            RDFS.label,
            Literal(str(article.name), datatype=XSD.string)
        ))

        # source document (Wiki article url)
        source_uri: URIRef = URIRef(article.url)
        base_graph.add((source_uri, RDF.type, FOAF.Document))
        base_graph.add((article_uri, DCTERMS.source, source_uri))

        if article.infobox_raw_text:
            raw_graph.add((
                article_uri,
                COY.hasRawHtml,
                Literal(str(article.infobox_raw_text), datatype=XSD.string)
            ))
        
        place_uri: Union[URIRef, None] = None
        if article.is_location or is_topic_article:
            place_uri = self.__add_place(base_graph, article)
            base_graph.add((place_uri, GN.wikipediaArticle, article_uri))

            if article.coordinates:
                self.__add_coordinates(base_graph, place_uri, article.coordinates)
            if article.infobox_coordinates:
                self.__add_coordinates(base_graph, place_uri, article.infobox_coordinates)

        # add wikidata entity stuff
        if article.wikidata_entity:
            wikidata_entity_uri = URIRef(article.wikidata_entity)

            if len(article.wikidata_osm_elements) >= 1:
                for osm_element in article.wikidata_osm_elements:
                    self.__add_osm_element(wikidata_entity_uri, osm_element)
            
            # link new entities to the wikidata entity
            # FIXME: Smells like owl:sameAs semantics is too strong here
            base_graph.add((article_uri, OWL.sameAs, wikidata_entity_uri))

            if place_uri is not None:
                # TODO: Check is owl:sameAs is valid here
                base_graph.add((place_uri, OWL.sameAs, wikidata_entity_uri))

            # add one-hop graph around wikidata entity to ohg graph
            one_hop_graphs += article.wikidata_one_hop_graph
        
            # add labels of classes which wikidata entity is instance of
            # (classes are URIs of wd:entity in 1hop graph)
            # classes_with_labels: Dict[str, str]
            # entity_id: str
            # label: str
            for entity_id, label in article.classes_with_labels.items():
                wikidata_class_entity_uri = URIRef(WD[entity_id])

                one_hop_graphs.add((
                    wikidata_class_entity_uri,
                    RDFS.label,
                    Literal(label, datatype=XSD.string)
                ))

                # delete old triple in dataset endpoint
                if self.delete_old_entities:
                    self.graph_consistency_keeper.delete_label_triples(
                        wikidata_class_entity_uri
                    )
        
        # add doc infos
        if article.date_published is not None:
            base_graph.add((
                article_uri,
                SCHEMA.datePublished,
                Literal(str(article.date_published), datatype=XSD.dateTime)
            ))

        if article.date_modified is not None:
            base_graph.add((
                article_uri,
                SCHEMA.dateModified,
                Literal(str(article.date_modified), datatype=XSD.dateTime)
            ))

        if article.name:
            base_graph.add((
                article_uri,
                SCHEMA.name,
                Literal(str(article.name), datatype=XSD.string)
            ))

        if article.headline:
            base_graph.add((
                article_uri,
                SCHEMA.headline,
                Literal(str(article.headline), datatype=XSD.string)
            ))
        
        # add OSM elements of links texts from infoboxes' 'Location' values to the article
        location_infobox_rows: List[InfoboxLocationRow] = [
            row
            for row in article.infobox_rows.values()
            if isinstance(row, InfoboxLocationRow)
        ]

        for row in location_infobox_rows:
            for links in row.value_links:
                self.__add_osm_element(
                    article_uri,
                    row.value_osm_elements_links[links]
                )
            
        # delete old triples in dataset endpoint
        if self.delete_old_entities:
            self.graph_consistency_keeper.delete_article_and_location_triples(
                article_uri
            )

        return article_uri, place_uri

    @staticmethod
    def __add_isodatetime_from_date(
            target_graph: Graph,
            target_uri: URIRef,
            date_: datetime.date
    ):
        datetime_: datetime.datetime = datetime.datetime(
            date_.year,
            date_.month,
            date_.day
        )

        target_graph.add((
            target_uri,
            COY.hasMentionDate,
            Literal(datetime_, datatype=XSD.dateTime)
        ))

    def store_event(self, event: Event):
        base_graph = self.graphs['base']
        raw_graph = self.graphs['raw']

        # add all existing articles
        all_articles: List[Article] = event.get_linked_articles()
        
        wikidata_location_article_uris = [
            article.wikidata_entity
            for article in all_articles
            if article.wikidata_entity and article.is_location
        ]

        # URIs
        event_uri = self.__get_event_uri(event)
        context_uri = self.__get_context_uri(event)

        ## Event triples
        base_graph.add((event_uri, RDF.type, COY.NewsSummary))  # FIXME: Incompatible types
        base_graph.add((event_uri, RDF.type, COY.WikiNews))  # FIXME: Incompatible types
        base_graph.add((event_uri, RDF.type, COY.Event))  # FIXME: Incompatible types

        base_graph.add((
            event_uri,
            RDFS.label,
            Literal(event.text, datatype=XSD.string)
        ))
        
        base_graph.add((event_uri, COY.isIdentifiedBy, context_uri))

        if event.category:
            base_graph.add((
                event_uri,
                COY.hasTag,
                Literal(event.category, datatype=XSD.string)
            ))
        
        self.__add_isodatetime_from_date(base_graph, event_uri, event.date_)

        raw_graph.add((
            event_uri,
            COY.hasRawHtml,
            Literal(str(event.raw_text), datatype=XSD.string)
        ))

        # connect with topic
        # topic: Topic
        for topic in event.parent_topics:
            parent_event = self.__get_event_uri(topic)
            base_graph.add((event_uri, COY.isOccuringDuring, parent_event))

        # wikidata type
        # event_types: Dict[str, str]
        for entity_id, label in event.event_types.items():
            class_uri: URIRef = WD[entity_id]

            base_graph.add((event_uri, COY.hasWikidataEventType, class_uri))
            base_graph.add((
                class_uri,
                RDFS.label,
                Literal(label, datatype=XSD.string)
            ))

        # source (https://en.wikipedia.org/wiki/Portal:Current_events/...)
        source_uri = URIRef(event.source_url)
        base_graph.add((source_uri, RDF.type, FOAF.Document))

        # the news sources from behind the event summary
        for link in event.source_links:
            source_link_uri = URIRef(link.href)

            base_graph.add((context_uri, DCTERMS.source, source_link_uri))
            base_graph.add((source_link_uri, RDF.type, COY.News))  # FIXME

            base_graph.add((
                source_link_uri,
                RDFS.label,
                Literal(link.text, datatype=XSD.string)
            ))

            # delete old triples in dataset endpoint
            if self.delete_old_entities:
                self.graph_consistency_keeper.delete_news_source_triples(
                    source_link_uri
                )

        # the news sources referenced through [xx] down below.
        for source_reference in event.source_references:
            source_link_uri = URIRef(source_reference.url)

            base_graph.add((context_uri, DCTERMS.source, source_link_uri))
            base_graph.add((source_link_uri, RDF.type, COY.News))  # FIXME

            base_graph.add((
                source_link_uri,
                RDFS.label,
                Literal(source_reference.anchor_text, datatype=XSD.string)
            ))

            # delete old triples in dataset endpoint
            if self.delete_old_entities:
                self.graph_consistency_keeper.delete_news_source_triples(
                    source_link_uri
                )

        # sentences
        # event.sentences: List[Sentence]
        for sentence_index, sentence in enumerate(event.sentences):
            sentence_uri: URIRef = self.__get_sentence_uri(context_uri, sentence_index)

            base_graph.add((
                sentence_uri,
                RDFS.label,
                Literal(sentence.text, datatype=XSD.string)
            ))

            # links per sentence as nif:Phrase
            # sentence.links: List[Link]
            for link_index, link in enumerate(sentence.links):
                article: Article = link.article

                # link
                link_uri: URIRef = self.__get_phrase_uri(sentence_uri, link_index)

                base_graph.add((
                    link_uri,
                    RDFS.label,
                    Literal(link.text, datatype=XSD.string)
                ))

                # article
                if article is not None:
                    article_uri, _ = self.__add_article_triples(article)
                    base_graph.add((link_uri, GN.wikipediaArticle, article_uri))

                    # optimize searching for articles by wikidata entity
                    wikidata_entity_to_article = {
                        article.wikidata_entity: article
                        for article in all_articles
                        if article and article.wikidata_entity
                    }

                    # link wikidata entities with parent locations in this
                    # sentence (e.g. NY with USA)
                    for parent_wikidata_entity in article.parent_locations_and_relation:
                        # don't link reflexively (e.g. USA links USA as its country)
                        if parent_wikidata_entity in wikidata_location_article_uris and \
                                not article.wikidata_entity == parent_wikidata_entity:

                            parent_location_article = wikidata_entity_to_article[parent_wikidata_entity]
                            parent_location_place_uri = self.__get_place_uri(parent_location_article)
                            place_uri = self.__get_place_uri(article)

                            base_graph.add((
                                place_uri,
                                COY.isLocatedIn,
                                parent_location_place_uri
                            ))

        # delete old triples in dataset endpoint
        if self.delete_old_entities:
            self.graph_consistency_keeper.delete_news_summary_triples(
                event_uri
            )

    def store_topic(self, topic: Topic):
        base_graph = self.graphs['base']
        raw_graph = self.graphs['raw']

        # Event triples
        event_uri: URIRef = self.__get_event_uri(topic)

        base_graph.add((event_uri, RDF.type, COY.TextTopic))  # FIXME: Incompatible types
        base_graph.add((event_uri, RDF.type, COY.WikiNews))  # FIXME: Incompatible types
        base_graph.add((event_uri, RDF.type, COY.Event))  # FIXME: Incompatible types

        base_graph.add((
            event_uri,
            RDFS.label,
            Literal(topic.text, datatype=XSD.string)
        ))
        
        # store date of usage of this topic
        self.__add_isodatetime_from_date(base_graph, event_uri, topic.date)

        # store raw html element of this topic
        raw_graph.add((
            event_uri,
            COY.hasRawHtml,
            Literal(topic.raw_text, datatype=XSD.string)
        ))

        # connect to parent topics
        if topic.parent_topics is not None:
            for parent_topic in topic.parent_topics:
                parent_event = self.__get_event_uri(parent_topic)

                base_graph.add((event_uri, COY.isOccuringDuring, parent_event))
        
        if topic.article is not None:
            base_graph.add((event_uri, RDF.type, COY.ArticleTopic))  # FIXME

            # add article
            # Tuple[URIRef, Optional[URIRef]]
            article_uri, place_uri = \
                self.__add_article_triples(topic.article, is_topic_article=True)

            base_graph.add((event_uri, GN.wikipediaArticle, article_uri))

            # connect place with event
            if place_uri is not None:
                base_graph.add((event_uri, COY.hasLocation, place_uri))
            
            # add timespan
            timespan_uri: Optional[URIRef] = self.__add_timespan(
                base_graph, topic.article
            )

            if timespan_uri is not None:
                base_graph.add((event_uri, COY.hasTimespan, timespan_uri))
        
        # delete old triples in dataset endpoint
        if self.delete_old_entities:
            self.graph_consistency_keeper.delete_topic_triples(event_uri)

    def __load_graph(self, filename: str, dest_graph: Graph):
        path: Path = self.outputFolder / filename

        with open(path, 'r', encoding='utf-8') as f:
            dest_graph.parse(file=f)
        
    def load(self, file_prefix: str):
        for name, graph in self.graphs.items():
            self.__load_graph(file_prefix + '_' + name + '.jsonld', graph)

    def reset(self):
        for name in self.graphs:
            self.graphs[name] = Graph()

    def __save_graph(self, graph: Graph, filename: str):
        path: Path = self.outputFolder / filename
        graph.serialize(path, format='json-ld')
        logger.info(f'Graph saved to {path}')

    def save(self, file_prefix: str):
        for name in self.graphs.keys():
            filename = file_prefix + '_' + name + '.jsonld'
            self.__save_graph(self.graphs[name], filename)

    def exists(self, file_prefix: str):
        for graph_name in self.graphs.keys():
            filename = file_prefix + '_' + graph_name + '.jsonld'
            if not exists(self.outputFolder / filename):
                return False
        return True
