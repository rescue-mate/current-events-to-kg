# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
from typing import Dict, List, Optional

from rdflib import Graph

from currenteventstokg.model.infoboxrow import InfoboxRow
from currenteventstokg.model.osmElement import OSMElement


class Article:
    def __init__(
            self,
            url: str,
            is_location: bool,
            coordinates: Optional[List[float]],
            infobox_raw_text: str,
            infobox_rows: Dict[str, InfoboxRow],
            infobox_coordinates:Optional[List[float]],
            wikidata_osm_elements: List[OSMElement],
            wikidata_entity: str,
            wikidata_one_hop_graph: Graph,
            parent_locations_and_relation: Dict[str, List[str]], 
            classes_with_labels: Dict[str, str],
            microformats: Dict[str, datetime.datetime],
            date_published: str,
            date_modified: str,
            name: str,
            headline: str
    ):
        self.url: str = url
        self.is_location: bool = is_location
        self.coordinates: Optional[List[float]] = coordinates
        self.infobox_raw_text: str = infobox_raw_text.strip()
        self.infobox_rows: Dict[str, InfoboxRow] = infobox_rows
        self.infobox_coordinates: Optional[List[float]] = infobox_coordinates
        self.wikidata_osm_elements: List[OSMElement] = wikidata_osm_elements
        self.wikidata_entity: str = wikidata_entity
        self.wikidata_one_hop_graph: Graph = wikidata_one_hop_graph

        self.parent_locations_and_relation: Dict[str, List[str]] = \
            parent_locations_and_relation

        # classes_with_labels: wikidata classes, where the wd entity of this
        # article is an instance of
        self.classes_with_labels: Dict[str, str] = classes_with_labels

        self.microformats: Dict[str, datetime.datetime] = microformats
        self.date_published: str = date_published
        self.date_modified: str = date_modified
        self.name: str = name.strip()
        self.headline: str = headline.strip()
