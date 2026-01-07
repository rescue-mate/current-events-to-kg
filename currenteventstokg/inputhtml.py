# Copyright: (c) 2022, Lars Michaelis, Patrick Westphal
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import logging
import os.path
import re
from pathlib import Path
from typing import Optional, Tuple

import requests
from requests import Response
from zstandard import ZstdCompressor, ZstdDecompressor

from .sleeper import Sleeper


logger = logging.getLogger(__name__)


class InputHtml(Sleeper):
    def __init__(
            self,
            cache_dir: Path,
    ):
        super().__init__()

        self.cache_wiki_dir = cache_dir / 'wiki/'
        os.makedirs(self.cache_wiki_dir, exist_ok=True)

        self.cache_current_events_dir = cache_dir / 'current_events/'
        os.makedirs(self.cache_current_events_dir, exist_ok=True)

        self.cache_infobox_templates_dir = cache_dir / 'infobox_templates/'
        os.makedirs(self.cache_infobox_templates_dir, exist_ok=True)

        self.compressor = ZstdCompressor(threads=-1)
        self.decompressor = ZstdDecompressor()

    def __fetch_compressed_page(
            self,
            page_file_path: Path,
            url: str
    ) -> str:

        compressed_page_file_path = Path(str(page_file_path) + '.zst')
        
        if os.path.exists(compressed_page_file_path):
            # open compressed file
            page_content: str = self.__load_and_decompress_page(compressed_page_file_path)

            return page_content
        
        elif os.path.exists(page_file_path):
            # open normal file extracted with older versions
            page_content: str = self.__load_page(page_file_path, compressed_page_file_path)

            return page_content

        else:
            # get and store compressed
            page: Optional[Response] = self.__request_with_three_trials(url)

            if page is None:
                return ''

            self.__compress_and_store_page(page.text, compressed_page_file_path)

            return page.text  

    def __compress_and_store_page(self, page_content: str, compressed_page_file_path: Path):
        compressed_page_content = self.compressor.compress(page_content.encode('utf-8'))

        with open(compressed_page_file_path, mode='wb') as f:
            f.write(compressed_page_content)

    def __load_and_decompress_page(self, compressed_page_file_path: Path) -> str:
        with open(compressed_page_file_path, mode='rb') as f:
            compressed_page_content: bytes = f.read()
        
        page_content = self.decompressor.decompress(compressed_page_content)
        page_content = page_content.decode('utf-8')

        return page_content

    def __load_page(self, page_file_path: Path, compressed_page_file_path: Path) -> str:
        with open(page_file_path, mode='r', encoding='utf-8') as f:
            page_content: str = f.read()
        
        # store compressed and delete uncompressed
        self.__compress_and_store_page(page_content, compressed_page_file_path)
        os.remove(page_file_path)

        return page_content

    @staticmethod
    def __request_with_three_trials(url: str) -> Optional[Response]:
        for t in range(3):
            try:
                return requests.get(url)
            except Exception as e:
                logger.error('inputhtml.py HTTP request #' + str(t + 1))
                logger.error(e)
                if t == 2:
                    raise e

    def fetch_current_events_page(self, suffix) -> Tuple[str, str]:
        base_url = 'https://en.wikipedia.org/wiki/Portal:Current_events/'
        file_path = self.cache_current_events_dir / (suffix + '.html')
        source_url = base_url + suffix

        return (
            source_url,
            self.__fetch_compressed_page(
                page_file_path=file_path,
                url=source_url
            )
        )

    def fetch_wikipedia_page(self, url) -> str:
        base_url = 'https://en.wikipedia.org/wiki/'
        url_suffix = re.split('/', url)[-1]
        file_path = self.cache_wiki_dir / (url_suffix + '.html')
        
        return self.__fetch_compressed_page(
            page_file_path=file_path,
            url=base_url + url_suffix
        )

    def fetch_location_templates_page(self) -> str:
        url = 'https://en.wikipedia.org/wiki/Wikipedia:List_of_infoboxes/Place'
        file_path = self.cache_infobox_templates_dir / 'places.html'
        
        return self.__fetch_compressed_page(
            page_file_path=file_path,
            url=url
        )
