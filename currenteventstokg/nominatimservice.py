# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import logging
from logging import ERROR
from os import makedirs
from pathlib import Path

from OSMPythonTools import logger as osm_logger
from OSMPythonTools.cachingStrategy import JSON, CachingStrategy
from OSMPythonTools.nominatim import Nominatim

from typing import Dict


logger = logging.getLogger(__name__)


class NominatimService:
    # Limits : https://operations.osmfoundation.org/policies/nominatim/

    def __init__(
            self,
            basedir: Path,
            cache_dir: Path,
            program_name: str,
            program_version: str,
            program_git_repo: str,
            server_address: str,
            wait_between_queries: int = 5
    ):

        self.nominatim_cache_path = basedir / cache_dir / 'nominatim/'
        makedirs(self.nominatim_cache_path, exist_ok=True)
        
        self.user_agent_identifier = \
            program_name + '(bot)/' + program_version + ' (' + program_git_repo + ")"

        logger.info(f'nominatim server: {server_address}')
        logger.info(f'nominatim user-agent: {self.user_agent_identifier}')

        self._nominatim = Nominatim(
            endpoint=server_address,
            waitBetweenQueries=wait_between_queries,
            userAgent=self.user_agent_identifier
        )

        CachingStrategy.use(JSON, cacheDir=self.nominatim_cache_path)
        osm_logger.setLevel(ERROR)

    def __query(self, query_str, kwargs: Dict):
        last_exception = None

        for i in range(1, 4):
            try:
                res = self._nominatim.query(query_str, **kwargs)

                return res

            except Exception as e:
                last_exception = e
                logger.error(f'nominatimService.py query try #{i} failed:', e)

        raise last_exception

    def query(self, query_str: str):
        return self.__query(query_str, {'params': {'limit': 1}, 'wkt': True})

    def lookup(self, osm_id):
        return self.__query(osm_id, {'params': {'limit': 1}, 'wkt': True, 'lookup': True})
        