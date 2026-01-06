# Copyright: (c) 2022, Lars Michaelis, Patrick Westphal
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import logging
from atexit import register
from json import dump, dumps, load
from os.path import exists
from pathlib import Path
from typing import List, Tuple, Dict

import requests


logger = logging.getLogger(__name__)


class Falcon2Service:
    def __init__(
            self,
            basedir: Path,
            cache_dir: Path,
            falcon_service_url: str
    ):
        self.basedir: Path = basedir

        self.cache_path: Path = self.basedir / cache_dir / 'falcon2_entities_cache.json'
        self.text_to_entities: Dict = self.__load_json_dict(self.cache_path)

        if not falcon_service_url:
            self.url_long: str = 'https://labs.tib.eu/falcon/falcon2/api?mode=long&db=1'
        else:
            self.url_long: str = falcon_service_url

        self.headers: Dict[str, str] = {
            'content-type': 'application/json',
            'Accept-Charset': 'UTF-8'
        }

        # save caches after termination
        register(self.__save_caches)

    # cleaned
    def __save_caches(self):
        self.__save_json_dict(self.cache_path, self.text_to_entities)

    # cleaned
    @staticmethod
    def __load_json_dict(file_path: Path) -> Dict:
        if exists(file_path):
            with open(file_path, mode='r', encoding='utf-8') as f:
                return load(f)

        else:
            return {}

    # cleaned
    @staticmethod
    def __save_json_dict(file_path: Path, data: Dict):
        with open(file_path, mode='w', encoding='utf-8') as f:
            dump(data, f)

    def query_sentence(self, text: str) -> Tuple[List[str], List[str]]:
        entities_wikidata = None
        entities_dbpedia = None

        if text in self.text_to_entities:
            entities_wikidata, entities_dbpedia = self.text_to_entities[text]

        else:
            # convert into sendable string
            text_cleaned = text.replace('"','')
            text_cleaned = text_cleaned.replace("'","")
            text_cleaned = text_cleaned.replace('\n',' ')
            text_cleaned = dumps(text_cleaned)[1: -1]

            payload = '{"text":"' + text_cleaned + '"}'
            payload = payload.encode('utf-8')
            for i in range(2):
                try:
                    r = requests.post(
                        self.url_long,
                        data=payload,
                        headers=self.headers
                    )

                except Exception as e:
                    logger.error('Falcon2 request failed!')
                    logger.error(e)
                    continue
                    
                if r.status_code == 200:
                    response = r.json()

                    # remove brackets from wikidata iris
                    entities_wikidata = [ x['URI'] for x in response['entities_wikidata']]
                    entities_dbpedia = [ x['URI'] for x in response['entities_dbpedia']]

                    self.text_to_entities[text] = [entities_wikidata, entities_dbpedia]

                    break

                else:
                    logger.error(f'Falcon2 query #{i+1} failed! ({r.status_code}: {r.reason})')
                    logger.error(f'text={text}')
                    logger.error(f'query={text_cleaned}')

                    if r.status_code == 500:
                        # INTERNAL SERVER ERROR -> bad input
                        logger.error('Skipping query...')
                        return [], []
            
            # raise if query failed every time
            if entities_wikidata is None or entities_dbpedia is None:
                raise RuntimeError('Could not query Falcon2 API')

        return entities_wikidata, entities_dbpedia
