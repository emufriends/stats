"""Persistent authenticated Cloud Storage I/O for bounded-memory publication.

The SDK reuses its HTTP session and credentials instead of spawning a CLI per
object. Only an explicit NotFound means absence. Rewrites pin source versions;
uploads use CRC32C verification. Credentials/response bodies are never logged.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import gzip
import json
from pathlib import Path
import shutil
import tempfile


@lru_cache(maxsize=1)
def storage_client():
    from google.cloud import storage
    return storage.Client()


def blob(uri):
    if not uri.startswith('gs://') or '/' not in uri[5:]:
        raise ValueError('Expected a Cloud Storage object URI')
    bucket, key = uri[5:].split('/', 1)
    if not bucket or not key:
        raise ValueError('Expected a Cloud Storage object URI')
    return storage_client().bucket(bucket).blob(key)


def exists(uri):
    from google.api_core.exceptions import NotFound
    try:
        blob(uri).reload(timeout=60)
        return True
    except NotFound:
        return False
    except Exception:
        raise RuntimeError('could not verify publication object existence') from None


def object_state(uri):
    from google.api_core.exceptions import NotFound
    value = blob(uri)
    try:
        value.reload(timeout=60)
    except NotFound:
        return {'generation': 0, 'owner': None, 'crc32c': None}
    return {'generation': int(value.generation),
            'owner': (value.metadata or {}).get('ark_publication_transaction'),
            'crc32c': value.crc32c,
            'headers': {name: getattr(value, name) for name in
                        ('content_type', 'content_encoding', 'cache_control',
                         'content_disposition', 'content_language', 'metadata')}}


def copy_object(source_uri, destination_uri, *, expected_generation=None):
    source, destination = blob(source_uri), blob(destination_uri)
    source.reload(timeout=60)
    # Blob.rewrite sends destination metadata; absent fields can receive bucket
    # defaults rather than the source's values. Exact rollback must retain the
    # cache policy and gzip headers as well as the original object bytes.
    for attribute in ('content_type', 'content_encoding', 'cache_control',
                      'content_disposition', 'content_language', 'metadata'):
        setattr(destination, attribute, getattr(source, attribute))
    token = None
    while True:
        options = {'if_generation_match': expected_generation} if expected_generation is not None else {}
        token, _, _ = destination.rewrite(source, token=token,
            if_source_generation_match=int(source.generation), timeout=60, **options)
        if token is None:
            return


def delete_object(uri, *, expected_generation=None):
    from google.api_core.exceptions import NotFound
    try:
        options = {'if_generation_match': expected_generation} if expected_generation is not None else {}
        blob(uri).delete(timeout=60, **options)
    except NotFound:
        return


@contextmanager
def gzip_file(path):
    """Deterministic streaming gzip; never load a full Arena bundle into RAM."""
    with tempfile.NamedTemporaryFile(suffix='.gz', delete=False) as temporary:
        compressed = Path(temporary.name)
    try:
        with Path(path).open('rb') as source, compressed.open('wb') as output:
            with gzip.GzipFile(filename='', mode='wb', fileobj=output, compresslevel=6, mtime=0) as target:
                shutil.copyfileobj(source, target, length=1024*1024)
        yield compressed
    finally:
        compressed.unlink(missing_ok=True)


def upload(path, uri, *, content_type, cache_control, compressed=True, immutable=False,
           expected_generation=None, owner=None):
    destination = blob(uri)
    destination.content_type = content_type
    destination.cache_control = cache_control
    destination.content_encoding = 'gzip' if compressed else None
    if owner:
        destination.metadata = {**(destination.metadata or {}), 'ark_publication_transaction': owner}
    options = {'content_type': content_type, 'timeout': 120, 'checksum': 'crc32c'}
    if immutable:
        options['if_generation_match'] = 0
    elif expected_generation is not None:
        options['if_generation_match'] = expected_generation
    if compressed:
        with gzip_file(path) as encoded:
            destination.upload_from_filename(str(encoded), **options)
    else:
        destination.upload_from_filename(str(path), **options)


def read_json(uri):
    from google.api_core.exceptions import NotFound
    try:
        payload = blob(uri).download_as_bytes(timeout=60)
    except NotFound:
        return {}
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON control object')
    return value
