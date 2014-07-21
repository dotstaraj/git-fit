from subprocess import Popen as popen, PIPE
from fitlib import DataStore
from os import environ, devnull

_s3keys_from_odin_cmd='''
python2.7 -c "
from json import load as loadjson
from base64 import b64decode
from urllib2 import urlopen

odin_query_url='http://localhost:2009/query?Operation=retrieve&ContentType=JSON&material.materialName={0}&material.materialType='
getOdinMaterial = lambda m: b64decode(loadjson(urlopen(odin_query_url + m))['material']['materialData'])

try:
    print getOdinMaterial('Principal')
    print getOdinMaterial('Credential')
except:
    exit(1)
"
'''

_TRANSFER_CHUNK_SIZE = 102400
S3Connection = None
def _getKeys():
    materialName = 'com.amazon.access.krf-dev-build-krf-git-1'
    userAndHost = 'krf.aka.amazon.com'
    if 'KRFBUILD_USER' in environ and environ['KRFBUILD_USER']:
        userAndHost = environ['KRFBUILD_USER'] + '@' + userAndHost
    proc = popen(['ssh', '-o', 'StrictHostKeyChecking=no', userAndHost, _s3keys_from_odin_cmd.format(materialName)], stdout=PIPE, stderr=open(devnull, 'wb'))
    creds = proc.communicate()[0].split()
    if proc.returncode:
        raise Exception('Error getting AWS access credentials!')
    return creds

def _getBucket():
    global S3Connection
    if not S3Connection:
        # importing boto library adds on a huge chunk of startup time for
        # every invocation of fit, so import it only right before we ever
        # actually need it
        from boto.s3.connection import S3Connection as s3conn
        S3Connection = s3conn

    return S3Connection(*_getKeys()).get_bucket('krfdirect-git-repo')

class Store(DataStore):
    def __init__(self, progress):
        self.bucket = _getBucket()
        self.progress = progress

    def get(self, key, dst, size):
        if key:
            key.get_contents_to_filename(dst, cb=self.progress, num_cb=size/_TRANSFER_CHUNK_SIZE)
            return True

    def put(self, src, dst, size):
        # S3 uploads are atomic. So if a file upload is interrupted, it will be as if none of
        # it was uploaded at all. So transient temporary transfer location is not needed like
        # it is when *downloading* from S3
        try:
            self.bucket.new_key(dst).set_contents_from_filename(src, cb=self.progress, num_cb=size/_TRANSFER_CHUNK_SIZE)
            return True
        except:
            return False

    def check(self, key):
        return self.bucket.get_key(key)
