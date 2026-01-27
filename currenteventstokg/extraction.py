# Copyright: (c) 2022-2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import copy
import datetime
import re
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple, Union, Set

from bs4 import BeautifulSoup, NavigableString, Tag, PageElement

from .inputhtml import InputHtml
from .objects.article import Article
from .outputrdf import OutputRdf
from .util import month_name_to_int
from .objects.event import Event
from .objects.link import Link
from .objects.reference import Reference
from .objects.sentence import Sentence
from .objects.topic import Topic
from .articleextractor import ArticleExtractor


class Extraction:
    def __init__(
            self,
            basedir: Path,
            input_html: InputHtml,
            output_data: OutputRdf,
            article_extractor: ArticleExtractor
    ):
        self.basedir: Path = basedir
        self.input_html: InputHtml = input_html
        self.output_data: OutputRdf = output_data
        self.article_extractor: ArticleExtractor = article_extractor
        self.article_recursions: int = 2

    def __parse_event_tag_recursive(
            self,
            html_element: Tag,
            links: List[Link] = None,
            source_links: List[Link] = None,
            start_index: int = 0
    ) -> Tuple[str, List[Link], List[Link]]:

        text = ''
        current_index = start_index

        if not links and not source_links:
            links: List[Link] = []
            source_links: List[Link] = []

        for child_element in html_element.children:
            if isinstance(child_element, NavigableString):
                text += child_element
                current_index += len(child_element)
                
            elif isinstance(child_element, Tag):
                # skip citations in <sup> tags
                if child_element.name == 'sup':
                    continue

                recognized_text, recognized_links, recognized_source_links =  \
                    self.__parse_event_tag_recursive(
                        child_element, links, source_links, current_index
                    )
                text_length: int = len(recognized_text)

                is_source_link = False

                # extract link
                if child_element.name == 'a':
                    href = child_element['href']

                    # add url prefix to urls from wikipedia links
                    if href[0] == '/':
                        href = 'https://en.wikipedia.org' + href

                    if 'class' in child_element.attrs and 'external' in child_element['class']:
                        if recognized_text.startswith('(') and recognized_text.endswith(')'):
                            is_source_link = True
                    
                    new_link: Link = Link(
                        href,
                        recognized_text,
                        current_index,
                        current_index + text_length
                    )

                    if is_source_link:
                        source_links.append(new_link)
                    else:
                        links.append(new_link)

                if not is_source_link:
                    text += recognized_text
                
                current_index += text_length

            else:
                raise Exception()

        return text, links, source_links

    def __parse_topic(
            self,
            html_list: Tag,
            parent_topics: List[Topic],
            date_obj: datetime.date,
            num_topics: int,
            source_url_str: str
    ) -> Generator[Topic]:
        # create tag with content until ul
        soup = BeautifulSoup('<li></li>', 'lxml')
        topic_row: Tag = soup.find('li')

        for child in html_list.children:
            if hasattr(child, 'name') and child.name == 'ul':
                break

            topic_row.append(copy.copy(child))

        # str, List[Link]
        text, links = self.article_extractor.get_text_and_links_recursive(topic_row)
        text = text.strip().strip(':')

        if len(links) == 0:
            # topic row without link (e.g. 14.1.2022 #4)
            yield Topic(
                raw_text=str(topic_row),
                text=text,
                article=None,
                parent_topics=[],
                date_=date_obj,
                index=num_topics,
                source_url=source_url_str
            )

        else:
            # get topic labels
            link_to_topic_label: Dict[Link, str] = {}

            if len(links) == 1:
                # use whole text as topic label
                link_to_topic_label[links[0]] = text

            elif len(links) > 1:
                # split text by comma seperator between links and use pieces for links
                # between each comma as topic labels
                topic_label_separators: Set[Tuple[int, int]] = set()

                # add commas outside of links to seperator list
                for match in re.finditer(r',', text):
                    in_link: bool = False
                    for link in links:
                        assert isinstance(link, Link)

                        if match.start() >= link.start_pos and match.end() <= link.end_pos:
                            in_link = True

                    if not in_link:
                        topic_label_separators.add((match.start(), match.end()))

                # assign topic labels
                if len(topic_label_separators) == 0:
                    # no text separators found => each topic link gets full text
                    for link in links:
                        link_to_topic_label[link] = text

                else:
                    # split text based on separators between links

                    # sort by start index
                    sorted_separators: List[Tuple[int, int]] = sorted(
                        list(topic_label_separators),
                        key=lambda separator_pair: separator_pair[0]
                    )

                    sorted_links = sorted(links, key=lambda lnk: lnk.start_pos)

                    current_seperator_index: int = 0 # current label end
                    label_start_position: int = 0
                    label_end_position: int = sorted_separators[current_seperator_index][0]

                    for link in sorted_links:
                        if link.end_pos > label_end_position:
                            # move to next label if link is after current end of label
                            if current_seperator_index + 1 < len(sorted_separators):
                                # move to next seperator if available
                                label_start_position = sorted_separators[current_seperator_index][0]
                                label_end_position = sorted_separators[current_seperator_index+1][0]
                                current_seperator_index += 1

                            else:
                                # use text end as last separator
                                label_start_position = sorted_separators[current_seperator_index][0]
                                label_end_position = len(text)
                            
                            label_start_position += 1 # skip "," seperator char
                        
                        label: str = text[label_start_position: label_end_position]
                        link_to_topic_label[link] = label.strip()
                
            # create topics
            for i, link in enumerate(links):
                # NOTE: article == None if href is redlink like on 27.1.2022
                article: Article = self.article_extractor.get_article(
                    url=link.href,
                    is_topic=True,
                    article_recursions_left=self.article_recursions
                )
                
                label: str = link_to_topic_label[link]

                # index of the topic
                topic_cunt: int = num_topics + i

                yield Topic(
                    raw_text=str(topic_row),
                    text=label,
                    article=article,
                    parent_topics=parent_topics,
                    date_=date_obj,
                    index=topic_cunt,
                    source_url=source_url_str
                )
    
    def __extract_reference_numbers_from_event(self, html_tag: Tag) -> List[int]:
        # html_tag is usually <li>

        reference_numbers: List[int] = []
        superscripts: List[PageElement] = html_tag.find_all('sup')

        for superscript in superscripts:
            if hasattr(superscript, 'attrs') and 'id' in superscript.attrs:
                superscript_id = str(superscript.attrs['id'])

                if superscript_id.startswith('cite_ref-'):
                    reference_nr: int = self.__get_nr_from_cite_note_id(superscript_id)

                    reference_numbers.append(reference_nr)
        
        return reference_numbers

    def __parse_event(
            self,
            li_tag: Tag,
            parent_topics: List[Topic],
            events_index: int,
            category: Optional[str],
            date_: datetime.date,
            source_url_str: str,
            references: Dict[int, Reference]
        ) -> Event:

        # parse
        text, links, source_links = self.__parse_event_tag_recursive(li_tag)

        # get articles behind links
        wiki_article_links: List[Link] = self.article_extractor.add_articles_to_wiki_links(
            links=links,
            is_topic = False,
            article_recursions_left = self.article_recursions
        )
        
        # split everything into sentences
        sentences: List[Sentence] = self.__split_event_text_into_sentences(
            event_text=text,
            wikipedia_links=wiki_article_links
        )
        
        # get types for this event from parent topics
        event_types: Dict[str, str] = self.__search_for_event_types_recursive(topics=parent_topics)

        # extract references/citations
        reference_numbers: List[int] = self.__extract_reference_numbers_from_event(html_tag=li_tag)

        # get references extracted from below
        referenced_sources: List[Reference] = [
            reference
            for nr, reference in references.items()
            if nr in reference_numbers
        ]

        return Event(
            raw_text=str(li_tag),
            parent_topics=parent_topics,
            text=text,
            source_url=source_url_str,
            date_=date_,
            sentences=sentences,
            source_links=source_links,
            event_types=event_types,
            event_index=events_index,
            category=category,
            source_references=referenced_sources
        )

    # split links occur, which are put into the sentence where they end in
    @staticmethod
    def __get_links_in_span(
            wikipedia_links: List[Link],
            sentence_start_index_in_whole_event_text: int,
            sentence_end_index_in_whole_event_text: int,
            link_offset: int
    ) -> List[Link]:

        link_index: int = link_offset
        sentence_links: List[Link] = []

        while link_index < len(wikipedia_links) and \
                wikipedia_links[link_index].end_pos <= sentence_end_index_in_whole_event_text:

            # switch context of link from event to sentence level
            link: Link = copy.copy(wikipedia_links[link_index])
            link.start_pos -= sentence_start_index_in_whole_event_text
            link.end_pos -= sentence_start_index_in_whole_event_text

            sentence_links.append(link)

        return sentence_links

    def __split_event_text_into_sentences(
            self,
            event_text: str,
            wikipedia_links: List[Link]
    ) -> List[Sentence]:

        text_length: int = len(event_text)
        sentences: List[Sentence] = []
        link_index: int = 0
        sentence_start_index: int = 0

        for sentence_match in re.finditer(r'\. ', event_text):  # FIXME: What about '!' and '?'?
            sentence_end_index: int = sentence_match.start() + 2
            
            # skip this guess of a sentence ending -> it's inside a link, links
            # usually don't span sentences
            if any([
                wikipedia_link.start_pos < sentence_end_index < wikipedia_link.end_pos
                for wikipedia_link in wikipedia_links
            ]):
                continue

            sentence_links = self.__get_links_in_span(
                    wikipedia_links,
                    sentence_start_index,
                    sentence_end_index,
                    link_index
            )

            sentences.append(
                Sentence(
                    event_text[sentence_start_index: sentence_end_index],
                    sentence_start_index,
                    sentence_end_index,
                    sentence_links
                )
            )

            sentence_start_index = sentence_end_index
            link_index += 1

        # if there are characters left and the last char in text is a '.', put
        # them in a last sentence if
        characters_left: bool = not sentence_start_index == text_length
        last_char_is_full_stop: bool = event_text[-1] == '.'

        if characters_left and last_char_is_full_stop:
            sentence_links: List[Link] = self.__get_links_in_span(
                wikipedia_links, sentence_start_index, text_length, link_index
            )

            sentences.append(
                Sentence(
                    event_text[sentence_start_index: text_length],
                    sentence_start_index,
                    text_length,
                    sentence_links
                )
            )

        # use everything as one sentence if no sentences have been found
        if len(sentences) == 0:
            sentence_links = self.__get_links_in_span(
                wikipedia_links, 0, text_length, 0
            )
            sentences.append(
                Sentence(
                    event_text, 0, text_length, sentence_links
                )
            )

        return sentences # doest have Source at the end
    
    def __search_for_event_types_recursive(self, topics: List[Topic]) -> Dict[str, str]:
        event_types: Dict[str, str] = {}
        
        for topic in topics:
            if topic.article is not None:
                event_types |= topic.article.classes_with_labels
        
        if len(event_types) == 0:
            for topic in topics:
                if topic.parent_topics:
                    _ev_types: Dict[str, str] = self.__search_for_event_types_recursive(topic.parent_topics)
                    event_types |= _ev_types
        
        return event_types

    # TODO: method is hard to understand
    def __extract_events_from_ul(
            self,
            unordered_html_list: Tag,
            category: Optional[str],
            date_: datetime.date,
            source_url: str,
            references: Dict[int, Reference]
        ):

        number_of_topics: int = 0
        number_of_events: int = 0
        # extract events under their topics iteratively
        stack: List[List] = []  # stack with [parentTopics, li]

        def is_valid_li(tag: Tag):
            is_li_tag: bool = tag.name == 'li'
            has_mw_empty_elt_class: bool = \
                tag.has_attr('class') and 'mw-empty-elt' in tag.attrs['class']

            return is_li_tag and not has_mw_empty_elt_class

        li_tags: List[Tag] = unordered_html_list.find_all(is_valid_li, recursive=False)
        stack += [[[], li_tag] for li_tag in li_tags[::-1]]

        while len(stack) > 0:
            # get next li tag with its topics
            parent_topics, li_tag = stack.pop()

            # li has ul's ? topic : event
            ul = li_tag.find('ul')

            if ul is None:  # li == event
                event: Event = self.__parse_event(
                    li_tag,
                    parent_topics,
                    number_of_events,
                    category,
                    date_,
                    source_url,
                    references
                )

                self.output_data.store_event(event)
                number_of_events += 1
                
            else:  # li == topic(s)
                topics: List[Topic] = list(self.__parse_topic(
                    html_list=li_tag,
                    parent_topics=parent_topics,
                    date_obj=date_,
                    num_topics=number_of_topics,
                    source_url_str=source_url
                ))

                for topic in topics:
                    self.output_data.store_topic(topic)
                    number_of_topics += 1
                    
                # append sub-elements to stack
                sub_elements = ul.find_all('li', recursive=False)
                sub_elements_and_parent_topic: List = [
                    [topics, sub_topic]
                    for sub_topic in sub_elements[::-1]
                ]

                stack += sub_elements_and_parent_topic
        
        return

    @staticmethod
    def __get_nr_from_cite_note_id(id_str: str) -> int:
        return  int(id_str.split('-')[-1])

    def __extract_reference(self, html_list_item: Tag) -> Optional[Reference]:
        # 'id' in html_list_item.attrs was already checked before calling this method
        cite_note_id_nr: int = self.__get_nr_from_cite_note_id(str(html_list_item.attrs['id']))
        cite_tag: Tag = html_list_item.find('cite')

        if cite_tag is not None:
            # only news references
            if 'class' in cite_tag.attrs and 'news' in cite_tag.attrs['class']:
                anchor_tags = cite_tag.find_all('a')
                ref_links = []
                for anchor_tag in anchor_tags:
                    if 'href' in anchor_tag.attrs and \
                            'class' in anchor_tag.attrs and \
                            'external' in anchor_tag.attrs['class']:

                        url = anchor_tag.attrs['href']
                        anchor_text, _ = self.article_extractor.get_text_and_links_recursive(anchor_tag)
                        
                        return Reference(cite_note_id_nr, url, anchor_text)
            
    def __extract_references_from_page(self, page: BeautifulSoup) -> Dict[int, Reference]:
        references = {}

        # Get first HTML element with a .reflist class tag
        references_html_element: Tag = page.select_one('.reflist')
        if references_html_element is not None:
            references_ordered_html_list: Tag = references_html_element.select_one('.references')

            if references_ordered_html_list is not None: # handle reference section without references...
                assert references_ordered_html_list.name == 'ol'

                for html_list_item in references_ordered_html_list.children:
                    if hasattr(html_list_item, 'name') and \
                            html_list_item.name == 'li' and \
                            'id' in html_list_item.attrs:

                        assert isinstance(html_list_item, Tag)  # a <li> tag, to be precise

                        list_item_id = str(html_list_item.attrs['id'])

                        if list_item_id.startswith('cite_note-'):
                            reference: Reference = self.__extract_reference(html_list_item)
                            
                            if reference is not None:
                                assert reference.nr not in references.keys()
                                references[reference.nr] = reference
                
        return references

    def parse_page(self, source_url_str: str, raw_page_content: str, year: int, month_str: str):
        # e.g.: https://en.wikipedia.org/wiki/Portal:Current_events/January_2026
        soup = BeautifulSoup(raw_page_content, 'lxml')

        # get all links from all superscript [x] references from the bottom of the page
        references: Dict[int, Reference] = self.__extract_references_from_page(soup)

        monthly_start_day: int = 1
        monthly_end_day: int = 31

        # parse all available days
        for day in range(monthly_start_day, monthly_end_day+1):
            id_str: str = f'{year}_{month_str}_{day}'

            # select doesn't work, because id starts with number
            day_div_element: Tag = soup.find(attrs={'id': id_str})
            if day_div_element is not None:
                month: int = month_name_to_int[month_str]
                date_: datetime.date = datetime.date(year, month, day)

                ## get box with events of class .description
                # "normal" usage of {{Current events|year=2005|month=01|day=7|content= 
                description_div_element: Tag = day_div_element.select_one('.description')

                # case of {{Current events header|2005|01|08}} usage where a table is generated...
                if description_div_element is None:
                    table: Tag = day_div_element.find_next('table', attrs={'class': 'vevent'})
                    description_div_element: Tag = table.select_one('.description')

                    if description_div_element is None:
                        raise Exception(f'.description class tag not found for {id_str}')

                ## try getting category tags
                # two versions of headings are used (afaik):
                # <p><b>Health and environment</b></p>
                # <div class="current-events-content-heading" role="heading">Armed conflicts and attacks</div>
                def is_category(tag: Tag) -> bool:
                    is_p_tag_without_attrs: bool = tag.name == 'p' and len(tag.attrs) == 0
                    is_div_tag_with_current_events_content_heading_class_attr: bool = \
                        tag.name == 'div' and \
                        tag.has_attr('class') and \
                        'current-events-content-heading' in tag.attrs['class']

                    return is_p_tag_without_attrs \
                        or is_div_tag_with_current_events_content_heading_class_attr

                # In [27]: description_div_element.find_all(is_category, recursive=False)
                # Out[27]:
                # [<p><b>Armed conflicts and attacks</b>
                #  </p>,
                #  <p><b>Business and economy</b>
                #  </p>,
                #  <p><b>Disasters and accidents</b>
                #  </p>,
                #  <p><b>Health and environment</b>
                #  </p>,
                #  <p><b>International relations</b>
                #  </p>,
                #  <p><b>Law and crime</b>
                #  </p>,
                #  <p><b>Politics and elections</b>
                #  </p>]
                category_tags: List[Tag] = description_div_element.find_all(is_category, recursive=False)
                
                # create list of event lists
                event_lists: Dict[Union[str, None], Tag] = {} # Tag: <ul> list of <ul> lists of events with category str as key

                if len(category_tags) > 0:
                    # format with categories from 2004
                    for category_tag in category_tags:
                        assert isinstance(category_tag, Tag)

                        # Tuple[str, List[Link]]
                        category, _ = self.article_extractor.get_text_and_links_recursive(category_tag)
                        category = category.strip()

                        # In [30]: category_tags[0].find_next_sibling('ul')
                        # Out[30]:
                        # <ul>
                        #   <li><a href="/wiki/Yemeni_civil_war_(2014%E2%80%93present)" title="Yemeni civil war (2014–present)">Yemeni civil war</a>
                        #       <ul>
                        #           <li><a class="mw-redirect" href="/wiki/2025_Southern_Yemen_offensive" title="2025 Southern Yemen offensive">...</a>, ...</li>
                        #           <li>The STC announces a plan to hold an ...</li>
                        #       </ul>
                        #    </li>
                        # </ul>
                        unordered_html_events_list: Tag = category_tag.find_next_sibling('ul')

                        if unordered_html_events_list is not None: # in case of empty category blocks...
                            event_lists[category] = unordered_html_events_list
                else:
                    ## format where no categories are used prior to 2004
                    for child in description_div_element.children:
                        assert isinstance(child, Tag)

                        if hasattr(child, 'name') and child.name == 'ul':
                            event_lists[None] = child
                
                for category, unordered_html_events_list in event_lists.items():
                    self.__extract_events_from_ul(
                        unordered_html_events_list,
                        category,
                        date_,
                        source_url_str,
                        references
                    )

        return
