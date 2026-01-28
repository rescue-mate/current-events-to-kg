# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from typing import Optional

from currenteventstokg.model.article import Article


class Link:
    def __init__(
            self,
            href: str,
            text: str,
            start_pos: int,
            end_pos: int,
            article: Optional[Article] = None
    ):
        self.href: str = href
        self.text: str = text
        self.start_pos: int = start_pos
        self.end_pos: int = end_pos
        self.article: Optional[Article] = article
