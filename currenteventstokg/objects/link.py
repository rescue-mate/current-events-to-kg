# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from typing import Optional

from currenteventstokg.objects.article import Article


class Link:
    def __init__(
            self,
            href: str,
            text: str,
            start_pos: int,
            end_pos: int,
            external: bool = False,
            article: Optional[Article] = None
    ):
        self.href = href
        self.text = text
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.external = external
        self.article = article
