# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
from typing import Optional, List, Dict

from currenteventstokg.objects.article import Article
from currenteventstokg.objects.link import Link
from currenteventstokg.objects.osmElement import OSMElement

class InfoboxRow:
    def __init__(self, label: str, value: str, value_links: List[Link]):
        self.label: str = label
        self.value: str = value
        self.value_links: List[Link] = value_links

class InfoboxLocationRow(InfoboxRow):
    from currenteventstokg.objects.article import Article

    def __init__(
            self,
            label: str,
            value:str,
            value_links: List[Link],
            falcon2_wikidata_entities: List[str],
            falcon2_articles: List[Article],
            falcon2_dbpedia_entities:List[str],
            value_osm_element_links: Dict[Link, OSMElement]
    ):
        super().__init__(label, value, value_links)

        self.falcon2_wikidata_entities: List[str] = falcon2_wikidata_entities
        self.falcon2_articles: List[Article] = falcon2_articles
        self.falcon2_dbpedia_entities: List[str] = falcon2_dbpedia_entities
        self.value_osm_elements_links: Dict[Link, OSMElement] = value_osm_element_links

class InfoboxRowTime(InfoboxRow):
    def __init__(
            self,
            label: str,
            value: str,
            value_links: List[Link],
            start_time: datetime.time,
            end_time: Optional[datetime.time]
    ):
        super().__init__(label, value, value_links)
        self.start_time = start_time # XSD.time conform string
        self.end_time = end_time # XSD.time conform string

class InfoboxRowDate(InfoboxRow):
    def __init__(
            self,
            label: str,
            value: str,
            value_links: List[Link],
            start_date: Optional[datetime.datetime],
            end_date: Optional[datetime.datetime],
            ongoing: bool
    ):
        super().__init__(label, value, value_links)
        self.start_date = start_date
        self.end_date = end_date
        self.ongoing = ongoing
    