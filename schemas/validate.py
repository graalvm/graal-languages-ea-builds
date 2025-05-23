import json
import os
import urllib.request
from jsonschema import validate as json_validate
from multiprocessing.dummy import Pool as ThreadPool
import requests
import sys
GENERIC_EA_SCHEMA = 'generic-ea-schema.json'
LATEST_EA_JSON = 'latest-ea.json'
LATEST_EA_SCHEMA = 'latest-ea-schema.json'
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SCHEMAS_DIR = 'schemas'
VERSIONS_DIR = 'versions'


def validate(json_name, schema_name):
    print(f'Validating {json_name}...')
    with open(json_name) as f:
        json_contents = json.load(f)
    with open(os.path.join(ROOT_PATH, SCHEMAS_DIR, schema_name)) as f:
        schema_contents = json.load(f)
    json_validate(json_contents, schema_contents)
    print(f'  ... validates against {schema_name}')
    if schema_name == LATEST_EA_SCHEMA:
        builds = [json_contents]
        ensure_consistent_latest_urls_files(json_name, json_contents)
    else:
        builds = json_contents
        ensure_one_latest_build(json_name, builds)
    validate_builds(builds)
    print('  ... passes sanity checks and all its URLs exist')


def ensure_consistent_latest_urls_files(json_name, latest_build):
    download_base_url = latest_build['download_base_url']
    for file in latest_build['files']:
        download_url = f'{download_base_url}{file["filename"]}'
        url_arch = 'amd64' if file['arch'] == 'x64' else file['arch']
        url_filename = f'latest-{file["variant"]}-{file["platform"]}-{url_arch}.url'
        url_file_path = os.path.join(os.path.dirname(json_name), url_filename)
        with open(url_file_path) as f:
            url_contents = f.read() # use read as the file should only contain the url alone 
            assert download_url == url_contents, f'Latest urls do not match:\n - {download_url} is in {json_name}\n - {url_contents} is in {url_filename}'
    


def ensure_one_latest_build(json_name, builds):
    num_latest = sum([1 if build['latest'] else 0 for build in builds])
    assert num_latest == 1, f'Expected one latest build in {json_name}, got {num_latest}'


def validate_builds(builds):
    for build in builds:
        version = build['version']
        download_base_url = build['download_base_url']
        files = build['files']
        assert version in download_base_url, f'version not found in download_base_url: {json.dumps(build)}'
        assert all(version in file['filename'] for file in files), f'version not found in all filenames: {json.dumps(build)}'
        check_urls_exist(download_base_url, files)


def check_urls_exist(download_base_url, files):
    download_urls = [f'{download_base_url}{file["filename"]}{extension}' for extension in ['', '.sha256'] for file in files]
    with ThreadPool() as pool:
        pool.map(check_url_exists, download_urls)


def check_url_exists(download_url):
    try:
        response = requests.head(download_url,allow_redirects=True, timeout=60)
        if response.url != download_url:
            print(f"Redirected from {download_url} to {response.url}")


        response.raise_for_status()
        if response.status_code == 302 or response.status_code == 200:
            print(f"Got {response.status_code} for '{download_url}'")
        elif response.status_code == 618:
            print(f" Got {response.status_code} from '{download_url}'")
            print(" fallback with get method insted of head")
            try:
                response2 = requests.get(download_url, allow_redirects=True, timeout=60)
                response2.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Failure during getting artifact metadata from '{download_url}' root cause {e}")

        else:
            print(f" {response.status_code} for '{download_url}'")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Failure during getting artifact metadata from '{download_url}' root cause {e}")



if __name__ == '__main__':
    """
    Finds all JSON files in the current directory and its subdirectories,
    and prints the file path if the file is not a valid JSON.
    """
    for root, dirs, files in os.walk('.'):
        for file in files:
            file_path = os.path.join(root, file)
            if file == GENERIC_EA_SCHEMA or file == LATEST_EA_SCHEMA :
                continue
            if file.endswith('.json'):
                print(file_path)
                schema_name = LATEST_EA_SCHEMA if file == LATEST_EA_JSON else GENERIC_EA_SCHEMA
                validate(file_path, schema_name)
            if file.endswith('.url'):
                with open(file_path) as f:
                    print(f'Validating {file_path}...')
                    url_contents = f.read() # use read as the file should only contain the url alone 
                    check_url_exists(url_contents)
                    print('  ... passes check for URL exist')
    print('JSON & URLs validation successful')