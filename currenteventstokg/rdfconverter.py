import logging
from os import makedirs
from os.path import exists
from pathlib import Path
from typing import List

from rdflib import Graph


logger = logging.getLogger(__name__)


def jsonld_to_ttl(
        basedir: Path,
        base_file_name: str,
        graph_extensions: List[str]
) -> str:

    dataset_dir = basedir / './dataset/'
    ttl_file_output_dir = basedir / './dataset_ttl/'
    makedirs(ttl_file_output_dir, exist_ok=True)

    prefix = base_file_name.split('.')[0]
    prefix_dmy = '_'.join(prefix.split('_')[0:-1])

    ttl_file_name = prefix_dmy + '.ttl'
    ttl_file_output_path = ttl_file_output_dir / ttl_file_name

    if not exists(ttl_file_output_path):
        # load graph
        g = Graph()
        input_file_path = dataset_dir / base_file_name

        logger.info(f'Parsing {input_file_path}...')
        g.parse(input_file_path)

        for graph_extension in graph_extensions:
            input_file_path = dataset_dir / f'{prefix_dmy}_{graph_extension}.jsonld'

            logger.info(f"Parsing {input_file_path}...")
            g.parse(input_file_path)

        # convert and save
        logger.info(f'Saving to {ttl_file_output_path}...')
        g.serialize(str(ttl_file_output_path), format='turtle', encoding='utf-8')

    return ttl_file_name
