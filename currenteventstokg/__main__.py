# Copyright: (c) 2022-2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import argparse
import logging
from os.path import abspath, split
from pathlib import Path
from typing import List

from .articleextractor import ArticleExtractor
from .extraction import Extraction
from .falconservice import Falcon2Service
from .inputhtml import InputHtml
from .nominatimservice import NominatimService
from .outputrdf import OutputRdf
from .placetemplatesextractor import PlacesTemplatesExtractor
from .util import months
from .wikidataservice import WikidataService

logger = logging.getLogger(__name__)


def print_months(months: List[str]):
    for m in months:
        logger.info(m)


def print_unparsed_months(months: List[str]):
    if len(months) > 0:
        logger.info('These months were skipped due to Exceptions:')
        print_months(months)


if __name__ == '__main__':
    __progName__ = "current-events-to-kg"
    __progVersion__ = "1.0"
    __progGitRepo__ = "https://github.com/rescue-mate/current-events-to-kg"

    basedir, _ = split(abspath(__file__))
    basedir = Path(basedir)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        fromfile_prefix_chars='!'
    )

    # TODO: Remove this mechanism
    parser.add_argument(
        '-md', '--merged_dataset',
        action='store_true',
        type=bool,
        help='Creation a merged dataset of already parsed months.'
    )
    
    parser.add_argument(
        '-doe', '--delete_old_entities',
        action='store_true',
        type=bool,
        help='Will delete old entity versions of currently extracted entities '
             'in the graph of the dataset endpoint.'
    )
    
    parser.add_argument(
        '-s', '--start',
        action='store', 
        help='Start month to parse (inclusive) format: month/year',
        type=str
    )
    
    parser.add_argument(
        '-e', '--end',
        action='store', 
        help='Last month to parse (inclusive) format: month/year',
        type=str
    )
    
    parser.add_argument(
        '-cd', '--cache_dir',
        action='store', 
        help='Cache directory (relative to directory of main.py)',
        default='./cache/',
        type=str
    )
    
    parser.add_argument(
        '-dd', '--dataset_dir',
        action='store', 
        help='Dataset output directory (relative to directory of main.py)',
        default='./dataset/',
        type=str
    )
    
    parser.add_argument(
        '-we', '--wikidata_endpoint',
        action='store', 
        help='Sets the wikidata sparql endpoint for querying',
        default='https://query.wikidata.org/sparql',
        type=str
    )
    
    parser.add_argument(
        "-wrs", '--wikidata_request_spacing',
        action='store',
        type=int,
        help='Minimum seconds between requests to the wikidata endpoint (only '
             'change to values allowed by your endpoint!)',
        default=2
    )
    
    parser.add_argument(
        '-ne', '--nominatim_endpoint',
        action='store', 
        help='Sets the nominatim endpoint for querying',
        default='https://nominatim.openstreetmap.org/',
        type=str
    )
    
    parser.add_argument(
        '-nrs', '--nominatim_request_spacing',
        action='store', 
        type=int,
        help='Minimum seconds between requests to the nominatim endpoint (only '
             'change to values allowed by your endpoint!)',
        default=2
    )

    parser.add_argument(
        '-de', '--dataset_endpoint',
        action='store',
        help='Sets the sparql endpoint URL of the dataset from which data will '
             'be removed if the parent entities also exist in the graph.',
        type=str,
        required=False
    )

    parser.add_argument(
        '-des', '--dataset_endpoint_subgraph',
        action='store',
        type=str,
        help='The subgraph used for the dataset.'
    )

    parser.add_argument(
        '-deu', '--dataset_endpoint_username',
        action='store',
        type=str,
        help='The username used for the dataset sparql endpoint.'
    )

    parser.add_argument(
        '-dep', '--dataset_endpoint_pw',
        action='store',
        type=str,
        help='The password used for the dataset sparql endpoint.'
    )

    parser.add_argument(
        '-deat', '--dataset_endpoint_auth_type',
        action='store',
        help='The auth type used for the dataset sparql endpoint.',
        type=str,
        choices=['basic', 'digest'],
        default='basic'
    )
    
    args = parser.parse_args()

    merged_dataset: bool = args.merged_dataset
    delete_old_entities: bool = args.delete_old_entities
    monthly_end_day: int = args.monthly_end_day
    start: str = args.start
    end: str = args.end
    cache_dir: Path = Path(args.cache_dir)
    dataset_dir: Path = Path(args.dataset_dir)
    wikidata_endpoint: str = args.wikidata_endpoint
    wikidata_request_spacing: int = args.wikidata_request_spacing
    nominatim_endpoint: str = args.nominatim_endpoint
    nominatim_request_spacing: int = args.nominatim_request_spacing
    dataset_endpoint: str = args.dataset_endpoint
    dataset_endpoint_subgraph: str = args.dataset_endpoint_subgraph
    dataset_endpoint_username: str = args.dataset_endpoint_username
    dataset_endpoint_pw: str = args.dataset_endpoint_pw
    dataset_endpoint_auth_type: str = args.dataset_endpoint_auth_type

    input_html: InputHtml = InputHtml(
        cache_dir=basedir/cache_dir
    )

    places_extractor: PlacesTemplatesExtractor = PlacesTemplatesExtractor(
        basedir=basedir,
        cache_dir=cache_dir,
        input_html=input_html
    )

    rdf_output: OutputRdf = OutputRdf(
            basedir=basedir,
            dataset_endpoint=dataset_endpoint,
            dataset_endpoint_subgraph=dataset_endpoint_subgraph,
            dataset_endpoint_username=dataset_endpoint_username,
            dataset_endpoint_pw=dataset_endpoint_pw,
            dataset_endpoint_auth_type=dataset_endpoint_auth_type,
            delete_old_entities=delete_old_entities,
            output_folder=dataset_dir
    )

    nominatim = NominatimService(
        basedir=basedir,
        cache_dir=cache_dir,
        program_name=__progName__,
        program_version=__progVersion__,
        program_git_repo=__progGitRepo__,
        server_address=nominatim_endpoint,
        wait_between_queries=nominatim_request_spacing
    )
    wikidata = WikidataService(
        basedir=basedir,
        cache_dir=cache_dir,
        program_name=__progName__,
        program_version=__progVersion__,
        program_git_repo=__progGitRepo__,
        server_address=wikidata_endpoint,
        min_seconds_between_queries=wikidata_request_spacing
    )

    falcon = Falcon2Service(
        basedir=basedir,
        cache_dir=cache_dir,
        falcon_service_url='https://labs.tib.eu/falcon/falcon2/api?mode=long&db=1'
    )

    article_extractor = ArticleExtractor(
        basedir=basedir,
        input_html=input_html,
        nominatim=nominatim,
        wikidata=wikidata,
        falcon=falcon,
        places_extractor=places_extractor,
    )

    extraction: Extraction = Extraction(
        basedir=basedir,
        input_html=input_html,
        output_data=rdf_output,
        article_extractor=article_extractor
    )

    # start date (inclusive)
    start_month, start_year = start.split('/')
    start_month = int(start_month)
    start_year = int(start_year)

    # end date (inclusive)
    end_month, end_year = end.split('/')
    end_month = int(end_month)
    end_year = int(end_year)

    month_graphs = {'base': None, 'osm': None, 'raw': None, 'ohg': None}

    unparsed_months = []

    while start_year * 100 + start_month <= end_year * 100 + end_month:
        month_year = months[start_month - 1] + '_' + str(start_year)

        # define file prefix e.g. January_2022
        file_prefix = month_year

        if merged_dataset:
            rdf_output.load(file_prefix)

        else:
            # get current events page
            # str, str
            source_url, page = input_html.fetch_current_events_page(month_year)
            assert isinstance(source_url, str)
            assert isinstance(page, str)
            
            # parse if graphs do not exist
            if not rdf_output.exists(file_prefix):
                try:
                    # parse page
                    extraction.parse_page(source_url, page, start_year, months[start_month - 1])

                except KeyboardInterrupt as ki:
                    print_unparsed_months(unparsed_months)
                    raise ki

                # save
                rdf_output.save(file_prefix)

                # clear graphs for next month
                rdf_output.reset()

        # advance month for next iteration
        if start_month >= 12:
            start_month = 1
            start_year += 1
        else:
            start_month += 1

    if merged_dataset:
        logger.info('Saving merged dataset...')
        rdf_output.save('dataset')

    if unparsed_months:
        logger.info('These months were skipped due to Exceptions:')
        print_months(unparsed_months)
