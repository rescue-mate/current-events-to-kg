# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import datetime
from currenteventstokg.objects.topic import Topic
from currenteventstokg.objects.link import Link
from currenteventstokg.objects.sentence import Sentence
from currenteventstokg.objects.article import Article
from currenteventstokg.objects.reference import Reference

from typing import Dict, List, Optional


class Event:
    def __init__(
            self,
            raw_text: str,
            parent_topics: List[Topic],
            text: str,
            source_url: str,
            date_: datetime.date,
            sentences: List[Sentence],
            source_links: List[Link],
            event_types: Dict[str, str],
            event_index: int,
            category: Optional[str],
            source_references: List[Reference]
    ):

        self.raw_text: str = raw_text.strip()
        self.parent_topics: List[Topic] = parent_topics
        self.text: str = text.strip()

        # e.g. https://en.wikipedia.org/wiki/Portal:Current_events/January_2022
        self.source_url = source_url

        self.date_: datetime.date = date_
        self.sentences: List[Sentence] = sentences
        self.source_links: List[Link] = source_links #Links to eg a CNN article
        self.event_types: Dict[str, str] = event_types
        self.event_index: int = event_index # n-th event of the day
        self.category: Optional[str] = category
        self.source_references: List[Reference] = source_references

    def get_linked_articles(self) -> List[Article]:
        return [article for sentence in self.sentences for article in sentence.get_linked_articles()]

    def __str__(self):
        return 'raw[:100]:' + str(self.raw_text)[:100] + '\n' \
            + 'text:' + str(self.text) + '\n' \
            + 'parentTopics:' + str(self.parent_topics)+ '\n'
