# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from typing import List

from currenteventstokg.model.article import Article
from currenteventstokg.model.link import Link


class Sentence:
    def __init__(self, text: str, start_index: int, end_index: int, links: List[Link]):
        self.text: str = text
        self.start_index: int = start_index
        self.end_index: int = end_index
        self.links: List[Link] = links
    
    def get_linked_articles(self) -> List[Article]:
        return [l.article for l in self.links if l.article]
