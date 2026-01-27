# Copyright: (c) 2023, Lars Michaelis, Patrick Westphal
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
import json
import re
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Tuple, Set, Union
from urllib.parse import urldefrag
from os import makedirs
import logging


from bs4 import BeautifulSoup, NavigableString, Tag, PageElement
from rdflib import Graph, URIRef

from .datetimeparser import DateTimeParser
from .falconservice import Falcon2Service
from .inputhtml import InputHtml
from .lruCacheCompressed import lru_cache as lru_cache_compressed
from .nominatimservice import NominatimService
from .objects.article import Article
from .objects.infoboxRow import InfoboxRow, InfoboxRowDate, InfoboxLocationRow, InfoboxRowTime
from .objects.link import Link
from .objects.osmElement import OSMElement
from .placetemplatesextractor import PlacesTemplatesExtractor
from .wikidataservice import WikidataService


logger = logging.getLogger(__name__)


class ArticleExtractor:
    def __init__(
            self,
            basedir: Path,
            input_html: InputHtml,
            nominatim: NominatimService,
            wikidata: WikidataService,
            falcon: Falcon2Service,
            places_extractor: PlacesTemplatesExtractor  # has own InputHtml instance
    ):
        self.input_html: InputHtml = input_html
        self.nominatim: NominatimService = nominatim
        self.wikidata: WikidataService = wikidata
        self.falcon: Falcon2Service = falcon
        self.place_templates: Set[str] = places_extractor.get_templates()

        # debug logger init
        logdir = basedir / 'logs'
        makedirs(logdir, exist_ok=True)

        self.time_parse_error_logger = logging.getLogger('timeParseError')
        self.time_parse_error_logger.setLevel(logging.DEBUG)

        time_parse_logger_handler = logging.FileHandler(
            logdir/'timeParseError.log',
            encoding='utf-8'
        )

        time_parse_logger_handler.setFormatter(logging.Formatter('%(message)s'))
        self.time_parse_error_logger.addHandler(time_parse_logger_handler)

        self.date_parse_error_logger = logging.getLogger('dateParseError')
        self.date_parse_error_logger.setLevel(logging.DEBUG)

        date_parse_logger_handler = logging.FileHandler(
            logdir/'dateParseError.log',
            encoding='utf-8'
        )

        date_parse_logger_handler.setFormatter(logging.Formatter('%(message)s'))
        self.date_parse_error_logger.addHandler(date_parse_logger_handler)

    # TODO: Method too long
    # !!! check article_recursions_left > 0 or set it to a known value BEFORE calling this function
    @lru_cache_compressed(maxsize=10000, compressed=True)
    def get_article(
            self,
            url: str,
            is_topic: bool = False,
            article_recursions_left: int = 0
    ) -> Optional[Article]:

        # return none if url is not an article
        if not self.__is_article_url(url):
            return None
        
        # get page
        raw_page: str = self.input_html.fetch_wikipedia_page(url)
        soup = BeautifulSoup(raw_page, 'lxml')

        # extract coordinates and infobox
        coord: Optional[List[float]] = self.__try_get_coordinates_from_page(soup)
        infobox: Tag = soup.find('table', attrs={'class': 'infobox'})

        # find tag with the jsonld graph with page information
        # there are two of these, but I think they are always equal(?)
        article_graph_element: Tag = soup.find(
            'script',
            attrs={'type': 'application/ld+json'}
        )

        if article_graph_element is None:
            # if this is not present I take it as an indicator that this is not
            # an article, but redirect page etc. (not confirmed)
            return None
        
        # parse graph
        page_graph: Dict[str, str] = json.loads(article_graph_element.string)
        # get 'real' url of page, due to redirects etc
        graph_url = page_graph['url']
        
        # remove url fragments
        article_url = urldefrag(graph_url).url

        # tests again if it is e.g. redict page
        if not self.__is_article_url(article_url):
            return None
        
        # extract various info
        date_published = None
        if 'datePublished' in page_graph:
            date_published = str(page_graph['datePublished'])

        date_modified = None
        if 'dateModified' in page_graph:
            date_modified = str(page_graph['dateModified'])

        name = None
        if 'name' in page_graph:
            name = str(page_graph['name'])

        headline = None
        if 'headline' in page_graph:
            headline = str(page_graph['headline'])

        wikidata_entity_uri_str = None
        if 'mainEntity' in page_graph:
            wikidata_entity_uri_str = str(page_graph['mainEntity'])
        
        # extract json with page loading stats etc
        # (RLQ=window.RLQ||[]).push(function(){mw.config.set(    <here>     );});

        # (RLQ=window.RLQ||[]).push(
        #   function(){
        #       mw.config.set(
        #           {
        #               "wgHostname":"mw-web.eqiad.main-74855f5f99-g4fxk",
        #               "wgBackendResponseTime":157,
        #               "wgPageParseReport":
        #                   {
        #                       "limitreport":
        #                           {
        #                               "cputime":"0.842",
        #                               "walltime":"1.036",
        #                               ...
        #                               "timingprofile":
        #                                   [
        #                                       "100.00%  859.333      1 -total",
        #                                       " 16.72%  143.708      2 Template:Reflist",
        #                                       " 16.71%  143.559      1 Template:Geographical_coordinates",
        #                                       " 16.21%  139.331      1 Template:Navbox",
        #                                       " 13.51%  116.114      1 Template:Lang",
        #                                       " 12.84%  110.324      1 Template:Geodesy",
        #                                       " 12.63%  108.520      1 Template:Sidebar_with_collapsible_lists",
        #                                       "  8.41%   72.291      3 Template:Cite_book",
        #                                       "  7.21%   61.992      1 Template:Short_description",
        #                                       "  6.94%   59.618    129 Template:Image_label"
        #                                   ]
        #                           },
        #                       ...
        _stats_string = article_graph_element.find_previous_sibling('script').string[51:-5]
        _stats_json = json.loads(_stats_string)
        templates_used_in_article: Set[str] = set(re.findall(
            r'Template:\w+',
            str(_stats_json['wgPageParseReport']['limitreport']['timingprofile'])
        ))  # -> {'Template:Cite_book', 'Template:Geodesy',
            #     'Template:Geographical_coordinates', 'Template:Image_label',
            #     'Template:Lang', 'Template:Navbox', 'Template:Reflist',
            #     'Template:Short_description',
            #     'Template:Sidebar_with_collapsible_lists'}
        
        # decrement article recursion level tracker to stop infinite depth in article links
        article_recursions_left -= 1 
        if article_recursions_left < 0:
            article_recursions_left = 0
        
        # parse the infobox
        infobox_rows: Dict[str, InfoboxRow] = {}
        microformats: Dict[str, datetime.datetime] = {}
        infobox_coordinates: Optional[List[float]] = None

        if infobox:
            infobox_rows, microformats, infobox_coordinates = self.__parse_infobox(
                infobox,
                templates_used_in_article,
                is_topic,
                article_recursions_left
            )

        # check if page is a location
        is_location: bool = self.__test_if_page_is_location(soup, templates_used_in_article)

        # check for parent locations
        parent_locations_and_relation: Dict[str, List[str]] = \
            self.wikidata.get_higher_level_locations(wikidata_entity_uri_str)

        # check for OSM entities from the wikidata uri of this page
        osm_rel_ids: List[str] = []
        osm_objs: List[str] = []

        if wikidata_entity_uri_str:
            osm_rel_ids, osm_objs = self.wikidata.get_osm_entities(wikidata_entity_uri_str)

        # get one hop graph from wikidata around these pages wd URI
        wikidata_one_hop_graph = Graph()
        entity_label_dict = {}

        if wikidata_entity_uri_str:
            wikidata_one_hop_graph = self.wikidata.get_one_hop_subgraph(
                wikidata_entity_uri_str
            )

            # extract the "type" of this article through wikidata
            # extract article instance-classes with label
            entity_instances: List[str] = []
            query = Template("""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?i WHERE {
    <$e> wdt:P31 ?i .
}""").substitute(e=wikidata_entity_uri_str)

            query_result = wikidata_one_hop_graph.query(query)
            #for row in query_result:
            #    entity_instances.append(row.input_html)  # looks wrong, fix below

            for result_row in query_result['results']['bindings']:
                value: str = result_row['i']['value']
                if value.strip():
                    entity_instances.append(value)

            entity_label_dict: Dict[str, str] = \
                self.wikidata.get_entity_labels(entity_instances)

        # extract wikidata wkts
        wiki_locations = []
        if len(osm_rel_ids) >= 1:

            for relation_id in osm_rel_ids:
                relation = self.nominatim.lookup('relation/' + relation_id)

                relation_id = relation.id()
                relation_type = relation.type()
                relation_wkt = relation.wkt()

                if relation_id is not None and relation_type is not None and \
                        relation_wkt is not None:
                    wiki_locations.append(
                        OSMElement(relation.id(), relation.type(), relation.wkt())
                    )

        elif len(osm_objs) >= 1:
            for osm_obj_id in osm_objs:
                osm_obj = self.nominatim.lookup(osm_obj_id)

                osm_obj_id = osm_obj.id()
                osm_obj_type = osm_obj.type()
                osm_obj_wkt = osm_obj.wkt()

                if osm_obj_id is not None and osm_obj_type is not None and \
                        osm_obj_wkt is not None:
                    wiki_locations.append(
                        OSMElement(osm_obj.id(), osm_obj.type(), osm_obj.wkt())
                    )
        
        return Article(
            url=article_url,
            is_location=is_location,
            coordinates=coord,
            infobox_raw_text=str(infobox),
            infobox_rows=infobox_rows,
            infobox_coordinates=infobox_coordinates,
            wikidata_osm_elements=wiki_locations,
            wikidata_entity=wikidata_entity_uri_str,
            wikidata_one_hop_graph=wikidata_one_hop_graph,
            parent_locations_and_relation=parent_locations_and_relation,
            classes_with_labels=entity_label_dict,
            microformats=microformats,
            date_published=date_published,
            date_modified=date_modified,
            name=name,
            headline=headline
        )

    def add_articles_to_wiki_links(
            self,
            links: List[Link],
            is_topic: bool = False,
            article_recursions_left: int = 0
    ) -> List[Link]:
        """
        Given a list of links, this method removes all links not pointing to
        articles, and sets the target articles as the links `article` attribute,
        i.e., for an article link `l`, it sets the article `a` (a proper Article
        object generated via `self.get_article( )`) as `l.article = a` and
        returns the list of enriched article links
        """
        wiki_article_links = [l for l in links if self.__is_article_url(l.href)]

        if article_recursions_left > 0:
            for l in wiki_article_links:
                a = self.get_article(
                    l.href,
                    is_topic=is_topic,
                    article_recursions_left=article_recursions_left
                )

                l.article = a

        return wiki_article_links
    
    def get_text_and_links_recursive(
            self,
            page_element: PageElement,
            start_index: int = 0
    ) -> Tuple[str, List[Link]]:

        if isinstance(page_element, NavigableString):
            text = page_element.get_text()
            links = []

            return text, links

        elif isinstance(page_element, Tag):
            links = []
            children_text = ''
            next_child_start_index = start_index

            for child in page_element.children:
                child_text, child_links = self.get_text_and_links_recursive(
                    child,
                    next_child_start_index
                )

                children_text += child_text
                links += child_links
                next_child_start_index += len(child_text)

            # extract own link
            if page_element.name == 'a' and 'href' in page_element.attrs:
                href = page_element['href']

                # add url prefix to urls from wikipedia links
                if href[0] == '/':
                    href = 'https://en.wikipedia.org' + href
                
                new_link = Link(
                    href=href,
                    text=children_text,
                    start_pos=start_index,
                    end_pos=start_index+len(children_text)
                )

                links.append(new_link)
            
            return children_text, links
        else:
            raise RuntimeError(
                f'Unhandled type for page element {str(page_element)}, '
                f'type: {str(type(page_element))}'
            )

    @staticmethod
    def __is_article_url(url: str) -> bool:
        if re.match('https://en.wikipedia.org/wiki/\w*:', url):
            # 17.1.22 has link to category page in event text
            return False

        if re.match('https://en.wikipedia.org/wiki/', url):
            return True

        return False

    def __parse_infobox(
            self,
            infobox: Tag,
            templates: Set[str],
            is_topic: bool = False,
            article_recursions_left: int = 0
    ) -> Tuple[
            Dict[str, InfoboxRow],
            Dict[str, datetime.datetime],
            Optional[List[float]]
        ]:

        infobox_rows: Dict[str, InfoboxRow] = {}

        # locations: Dict[str, InfoboxRow]
        # coordinates: Optional[List[float]]

        # extract Locations
        locations, coordinates = self.__get_location_from_infobox(
            infobox=infobox,
            templates=templates,
            article_recursions_left=article_recursions_left
        )

        infobox_rows.update(locations)

        # extract Dates and Times
        microformats: Dict[str, datetime] = {}
        # rows: Dict[str, InfoboxRow] = {}

        if is_topic:
            labels = [str(th.string) for th in infobox.tbody.find_all('th') if th.string]

            rows, microformats = self.__get_date_and_time_from_topic_infobox(
                infobox=infobox,
                infobox_labels=labels  # all table head fields
            )

            if rows:
                infobox_rows |= rows
        
        return infobox_rows, microformats, coordinates

    def _get_text_and_links_from_date_value(self, value_tag: PageElement) -> Tuple[str, List[Link]]:
        text: str = ''
        links: List[Link] = []
        index: int = 0

        if isinstance(value_tag, NavigableString):
            text = value_tag.text
            links = []

            return text, links

        else:
            assert isinstance(value_tag, Tag)

            for child in value_tag.children:
                is_tag: bool = isinstance(child, Tag)
                is_span: bool = hasattr(child, 'name') and child.name == 'span'

                has_noprint_class: bool = hasattr(child, 'attrs') and \
                    'class' in child.attrs and 'noprint' in child.attrs['class']

                has_display_none: bool = hasattr(child, 'attrs') and \
                     'style' in child.attrs and 'display:none' in child.attrs['style']

                is_not_visible: bool = has_noprint_class or has_display_none

                if is_tag and is_span and is_not_visible:
                    continue

                elif isinstance(child, NavigableString) or \
                        (hasattr(child, 'name') and child.name in ['a', 'b', 'abbr', 'span']):

                    _text, _links = self.get_text_and_links_recursive(child, start_index=index)
                    index += len(_text)
                    text += _text
                    links += _links

                elif hasattr(child, 'name') and child.name == 'br':
                    text += '\n'
                    index += 1

                elif hasattr(child, 'name') and child.name in ['sup']:
                    continue

                else:
                    break

            return text, links

    def _extract_row_for_label_if_exists(
            self,
            infobox_labels: List[str],
            target_label: str,
            infobox: Tag
    ) -> Dict[str, InfoboxRow]:
        if target_label in infobox_labels:
            th = infobox.tbody.find('th', string=target_label)
            if th:
                td = th.find_next_sibling('td')
                text, links = self._get_text_and_links_from_date_value(td)

                return {target_label: InfoboxRow(target_label, text, links)}
        return {}

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime.datetime]:
        # format observed: 2021-01-25 (and 2021, but will be ignored)
        match = re.search(r'(?P<y>[0-9]{4})-(?P<m>[0-9]{2})-(?P<d>[0-9]{2})', date_str)
        if match:
            y: int = int(match.group('y'))
            m: int = int(match.group('m'))
            d: int = int(match.group('d'))

            return datetime.datetime(y, m, d)

        return None

    # TODO: Method too long; needs refactoring
    def __get_date_and_time_from_topic_infobox(
            self,
            infobox: Tag,
            infobox_labels: List[str]  # all table head fields
    ) -> Tuple[Dict[str, InfoboxRow], Dict[str, datetime.datetime]]:

        microformats = {}
        if 'vevent' in infobox.attrs['class']:
            dtstart_tag: Tag = infobox.find(
                'span', attrs={'class': 'dtstart'}, recursive=True
            )

            if dtstart_tag:
                dtstart_datetime = self._parse_date(dtstart_tag.text)

                if dtstart_datetime:
                    microformats['dtstart'] = dtstart_datetime

            dtend_tag: Tag = infobox.find(
                'span', attrs={'class': 'dtend'}, recursive=True
            )

            if dtend_tag:
                dtend_datetime = self._parse_date(dtend_tag.text)

                if dtend_datetime:
                    microformats['dtend'] = dtend_datetime

        # Date tags separated into 2 groups.
        # Both can have spans from start to end, but have different single date meaning.
        date_rows_beginnings: Dict[str, InfoboxRow] = {}
        for target_label in ['Start Date', 'Arrival Date', 'First outbreak', 'Date(s)', 'Date']:
            date_rows_beginnings |= self._extract_row_for_label_if_exists(
                infobox_labels=infobox_labels,
                target_label=target_label,
                infobox=infobox
            )

        date_rows_endings: Dict[str, InfoboxRow] = {}
        for target_label in ['End Date', 'Duration']:
            date_rows_endings |= self._extract_row_for_label_if_exists(
                infobox_labels=infobox_labels,
                target_label=target_label,
                infobox=infobox
            )

        time_rows: Dict[str, InfoboxRow] = {}
        time_rows |= self._extract_row_for_label_if_exists(
            infobox_labels=infobox_labels,
            target_label='Time',
            infobox=infobox
        )

        # Extract time
        res_rows: Dict[str, InfoboxRow] = {}

        for label, infobox_row in time_rows.items():
            date_time_str = re.sub(r'[–−]', r'-', infobox_row.value)
            time_dict = DateTimeParser.parse_times(date_time_str)

            if time_dict:
                time = time_dict['start']
                end_time = None
                if 'end' in time_dict:
                    end_time = time_dict['end']

                time_row = InfoboxRowTime(
                    label=infobox_row.label,
                    value=infobox_row.value,
                    value_links=infobox_row.value_links,
                    start_time=time,
                    end_time=end_time
                )

                res_rows[label] = time_row
            
            else:
                self.time_parse_error_logger.info(
                    f'{date_time_str} does not contain any time information'
                )

        # Extract date(span) and combine with time
        for i, date_rows in enumerate([date_rows_beginnings, date_rows_endings]):
            is_ending = bool(i)

            for label, infobox_row in date_rows.items():
                date_time_str = re.sub(r'[–−]', r'-', infobox_row.value)

                # filter out some frequent values which are no dates
                as_of = re.search(r"[aA]s of", date_time_str)
                if not as_of:
                    time_dict = DateTimeParser.parse_times(date_time_str)

                    start_time: datetime = None
                    end_time: datetime = None

                    if time_dict:
                        start_time = time_dict['start']

                        if 'end' in time_dict:
                            end_time = time_dict['end']

                    date_dict = DateTimeParser.parse_dates(date_time_str)
                    
                    if 'date' in date_dict:
                        date: datetime = date_dict['date']

                        until: datetime = None
                        ongoing: bool = False

                        if 'until' in date_dict:
                            until = date_dict['until']

                        elif 'ongoing' in date_dict:
                            ongoing = date_dict['ongoing']

                        # combine dates and times
                        if date and not until and not ongoing:
                            if start_time:
                                # eg 10.1.22 13:00
                                date = date.replace(
                                    hour=start_time.hour,
                                    minute=start_time.minute
                                )

                                if end_time:
                                    # eg 22.3.22 13:00-14:00
                                    until = date.replace(
                                        hour=end_time.hour,
                                        minute=end_time.minute
                                    )

                        elif start_time or end_time:
                            # eg 22.3.22-23.3.22 13:00(-14:00)
                            # time span discarded, as it is not a single span but multiple
                            self.date_parse_error_logger.info(f'Discarding {date_time_str}')
                        
                        if date and not until and not ongoing and is_ending:
                            until = date
                            date: datetime = None
                        
                        date_row = InfoboxRowDate(
                            label=infobox_row.label,
                            value=infobox_row.value,
                            value_links=infobox_row.value_links,
                            start_date=date,
                            end_date=until,
                            ongoing=ongoing
                        )

                        res_rows[label] = date_row
                    else:
                        self.date_parse_error_logger.info(
                            f'Discarding "{date_time_str}" since no date '
                            f'information was found'
                        )

        return res_rows, microformats

    def _get_text_and_links_from_location_element(self, parent_tag: Tag) -> Tuple[str, List[Link]]:
        # Example for parent tag:
        # <td class="infobox-data label">
        #   <a href="/wiki/7th_arrondissement_of_Paris" title="7th arrondissement of Paris">7th arrondissement</a>
        #   ,
        #   <a href="/wiki/Paris" title="Paris">Paris</a>
        #   , France
        #   <span style="display:none" data-plural="0"></span>
        # </td>
        location_str: str = ''
        location_links: List[Link] = []

        index = 0
        for child in parent_tag.children:
            if (isinstance(child, NavigableString) or
                    (isinstance(child, Tag) and child.name and child.name in ['a', 'b', 'abbr'])):

                sub_string, links = self.get_text_and_links_recursive(child, start_index=index)
                index += len(sub_string)
                location_str += sub_string
                location_links += links

            elif child.name and child.name == 'br':
                location_str += '\n'
                index += 1

            elif 'class' in child.attrs and 'flagicon' in child.attrs['class']:
                continue

            elif child.name and child.name in ['sup']:
                continue

            else:
                break

        return location_str, location_links

    def __get_location_from_infobox(
            self,
            infobox: Tag,
            templates: Set[str],
            article_recursions_left: int = 0
    ) -> Tuple[Dict[str, InfoboxRow], Optional[List[float]]]:

        rows: Dict[str, InfoboxRow] = {}
        coordinates: Union[List[float], None] = None

        ## Notes: 
        # Template:Infobox_election only flag img...

        # choose label based on template
        if any(t in templates for t in ['Template:Infobox_storm']):
            label = 'Areas affected'
        else:
            label = 'Location'
        
        # find location label tag
        table_body: Tag = infobox.tbody

        if not table_body:
            return rows, coordinates

        table_head: Tag = table_body.find(
            'th',
            string=label,
            attrs={'class': 'infobox-label'}
        )

        if not table_head:
            return rows, coordinates
        
        # find value tag
        td: Tag = table_head.find_next_sibling('td')
        div: Tag = td.find('div', attrs={'class': 'location'}, recursive=False)

        if div:
            location_element = div
        else:
            location_element = td
        
        # parse value
        if isinstance(location_element, NavigableString):
            location_text: str = location_element.text
            location_links: List[Link] = []

        else:
            location_text, location_links = \
                self._get_text_and_links_from_location_element(location_element)

        if location_text:
            # get entities about the location value from Falcon2 api
            falcon_wikidata_entities, falcon_dbpedia_entities = \
                self.falcon.query_sentence(location_text)

            # falcon_wikidata_entities: List[str]
            # falcon_dbpedia_entities: List[str]

            falcon_articles: List[Article] = []

            if article_recursions_left > 0:
                # get wikipedia articles from falcons wikidata entities
                wikidata_uris: List[URIRef] = [URIRef(e) for e in falcon_wikidata_entities]

                wikidata_uri_to_wikipedia_url_mappings: Dict[str, str] = \
                    self.wikidata.get_wikipedia_article_urls(wikidata_uris)

                wikipedia_urls_of_wikidata_entities: List[str] = \
                    list(wikidata_uri_to_wikipedia_url_mappings.values())

                for url in wikipedia_urls_of_wikidata_entities:
                    article: Article = self.get_article(
                        url=url,
                        is_topic=False,
                        article_recursions_left=article_recursions_left
                    )

                    # only use article if it is about a location to filter out some false results
                    if article and article.is_location:
                        falcon_articles.append(article)
            
            # get geo coordinates from infobox location value link labels
            location_link_to_osm_element = {}
            for location_link in location_links:
                res = self.nominatim.query(location_link.text)
                osm_id: str = res.id()
                osm_type: str = res.type()
                coordinates_wkt: str = res.wkt()

                location_link_to_osm_element[location_link] = \
                    OSMElement(
                        osm_id=osm_id,
                        osm_type=osm_type,
                        wkt=coordinates_wkt
                    )

            rows[label] = InfoboxLocationRow(
                label=label,
                value=location_text,
                value_links=location_links,
                falcon2_wikidata_entities=falcon_wikidata_entities,
                falcon2_articles=falcon_articles,
                falcon2_dbpedia_entities=falcon_dbpedia_entities,
                value_osm_element_links=location_link_to_osm_element
            )

        # extract coordinates from "Location" label
        degrees_minutes_seconds: Tag = td.find('span', attrs={'class': 'geo-dms'})

        if degrees_minutes_seconds:
            coordinates: List[float] = self.__parse_coordinates(degrees_minutes_seconds)
        
        return rows, coordinates

    def __parse_coordinates(self, coordinates_span: Tag) -> Optional[List[float]]:
        lat = coordinates_span.find(
            name='span',
            attrs={'class': 'latitude'},
            recursive=False
        )

        lon = coordinates_span.find(
            name='span',
            attrs={'class': 'longitude'},
            recursive=False
        )

        if lat and lon:
            return [
                self.__degrees_minutes_seconds_to_decimal_degrees(lat.string),
                self.__degrees_minutes_seconds_to_decimal_degrees(lon.string)
            ]

        else:
            return None

    @staticmethod
    def __degrees_minutes_seconds_to_decimal_degrees(degrees_minutes_seconds_str: str) -> float:
        parts =  re.split('[°′″]', degrees_minutes_seconds_str) # 36°13′50.3″N

        if len(parts) == 2:
            degrees, direction = parts
            minutes = 0
            seconds = 0

        elif len(parts) == 3:
            degrees, minutes, direction = parts
            seconds = 0

        elif len(parts) == 4:
            degrees, minutes, seconds, direction = parts

        else:
            raise Exception()
        
        # convert to point decimal
        if isinstance(degrees, str):
            degrees = degrees.replace(',','.')
            degrees = float(degrees)

        if isinstance(minutes, str):
            minutes = minutes.replace(',','.')
            minutes = float(minutes)

        if isinstance(seconds, str):
            seconds = seconds.replace(',','.')
            seconds = float(seconds)
        
        return (degrees + minutes/60 + seconds/3600) * (-1 if direction in ['W', 'S'] else 1)

    def __test_if_page_is_location(
            self,
            page: BeautifulSoup,
            templates: Set[str]
    ) -> bool:
        # tests for infobox template css classes
        if self.__test_if_page_is_location_css(page):
            return True

        # tests if templates match place templates
        if self.__test_if_page_is_location_template(templates):
            return True

        return False

    @staticmethod
    def __test_if_page_is_location_css(page: BeautifulSoup) -> bool:
        location_classes: List[str] = [
            'ib-settlement',
            'ib-country',
            'ib-islands',
            'ib-pol-div',
            'ib-school-district',
            'ib-uk-place'
        ]

        if page:
            for class_ in location_classes:
                if class_ in page.attrs['class']:
                    return True

        return False

    def __try_get_coordinates_from_page(self, page: BeautifulSoup) -> Optional[List[float]]:
        coordinates_node = page.find(attrs={'id': 'coordinates'})

        if coordinates_node:
            geo_dms_tag: Tag = coordinates_node.find('span', attrs={'class': 'geo-dms'})
            if geo_dms_tag:
                return self.__parse_coordinates(geo_dms_tag)

        return None
    
    def __test_if_page_is_location_template(self, templates: Set[str]) -> bool:
        # check if the templates set contains any place templates
        # ...or whether both sets are *not* disjoint
        if templates.isdisjoint(self.place_templates):
            return False
        else:
            return True
