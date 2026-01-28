# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from datetime import date
from currenteventstokg.model.article import Article
from typing import List, Optional


class Topic:
    def __init__(
            self,
            raw_text: str,
            text: str,
            article: Optional[Article],
            parent_topics: List['Topic'],
            date_: date,
            index: int,
            source_url: str
    ):
        self.raw_text: str = raw_text
        self.text: str = text
        self.parent_topics: List['Topic'] = parent_topics
        self.article: Optional[Article] = article
        self.date: date = date_
        self.index: int = index # n-th topic of the day [0-n]
        self.source_url: str = source_url
        
    def __str__(self):
        return 'raw[:100]:' + str(self.raw_text)[:100] + '\n' \
            + 'text:' + str(self.text) + '\n' \
            + 'parent_topics:' + str(self.parent_topics) + '\n'
