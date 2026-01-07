import logging

from bs4 import BeautifulSoup, Tag, ResultSet
from os.path import exists
from pathlib import Path
import json
from .inputhtml import InputHtml
import re
from typing import Set


logger = logging.getLogger(__name__)


class PlacesTemplatesExtractor:
    def __init__(self, basedir: Path, cache_dir: Path, input_html: InputHtml):
        self.basedir = basedir
        self.input_html = input_html

        self.templates_cache_path = self.basedir / cache_dir / 'places_templates.json'
    
    def get_templates(self) -> Set[str]:
        if exists(self.templates_cache_path):
            logger.info(f'Loading places templates from {self.templates_cache_path}')

            with open(self.templates_cache_path, mode='r', encoding='utf-8') as f:
                template_list = json.load(f)

                return set(template_list)

        else:
            page: str = self.input_html.fetch_location_templates_page()
            soup = BeautifulSoup(page, 'lxml')

            content: Tag = soup.find('div', class_='mw-parser-output')

            place_template_links: ResultSet = content.find_all(
                'a',
                string=lambda text: bool(re.match('Template:Infobox', str(text)))
            )

            hrefs = [
                str(l.attrs['href']).split('/')[-1]
                for l in place_template_links
            ]

            template_list = list(hrefs)

            # cache
            with open(self.templates_cache_path, mode='w', encoding='utf-8') as f:
                json.dump(template_list, f)

            return set(template_list)
