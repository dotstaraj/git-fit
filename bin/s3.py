from fit import cacheDir, fitDir, selfDir
from fit import PIPE, popen, path
from shutil import copyfile, move
from sys import stdout, path as syspath

_TRANSFER_CHUNK_SIZE = 102400
class _ProgressPrinter:
    def __init__(self, size):
        self.size = size
        self.done = 0
        self.itemName = ''
    def updateProgress(self, done, size):
        print '\rProgress: %6.2f%% overall      %6.2f%% %s'%(float(self.done+done)/self.size*100, float(done)/size*100, self.itemName),(' '*20)+('\b'*20),
        stdout.flush()

_s3keys_from_odin_cmd='''
python -c "
from json import load as loadjson
from base64 import b64decode
from urllib2 import urlopen
print b64decode(loadjson(urlopen('http://localhost:2009/query?Operation=retrieve&ContentType=JSON&material.materialName=com.amazon.access.krew-dev-krew-dev-1&material.materialType=Principal'))['material']['materialData'])
print b64decode(loadjson(urlopen('http://localhost:2009/query?Operation=retrieve&ContentType=JSON&material.materialName=com.amazon.access.krew-dev-krew-dev-1&material.materialType=Credential'))['material']['materialData'])
"
'''

S3Connection = None
def _getBucket():
    global S3Connection
    if not S3Connection:
        # importing boto library adds on a huge chunk of startup time for
        # every invocation of fit, so import it only right before we ever
        # actually need it
        syspath.append(path.join(selfDir, '../s3'))
        from boto.s3.connection import S3Connection as s3conn
        S3Connection = s3conn

    keys = popen(['ssh', 'ankujain-2.desktop.amazon.com', _s3keys_from_odin_cmd], stdout=PIPE).communicate()[0].split()
    return S3Connection(*keys).get_bucket('krew-git-fit')


def get(fitTrackedData, opts):
    need = []
    missing = []
    
    bucket = _getBucket()
    
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        if path.exists(filePath) and path.getsize(filePath) == 0:
            objPre, objSuf = objHash[:2], objHash[2:]
            objPath = path.join(cacheDir, objPre, objSuf)
            
            if path.exists(objPath):
                copyfile(objPath, filePath)
            else:
                key = bucket.get_key('%s/%s'%(objPre, objSuf))
                key and need.append((filePath, key, objPath, size)) or missing.append(filePath)

    totalSize = sum([size for f,k,o,size in need])

    if opts['transfer']:
        pp = _ProgressPrinter(totalSize)
        
        for filePath,key,objPath,size in need:
            pp.itemName = filePath
            
            # Copy download to temp file first, and then to actual object location
            # This is to prevent interrupted downloads from causing bad objects to be placed
            # in the objects cache
            tempTransferFile = path.join(fitDir, '.tempTransfer')
            key.get_contents_to_filename(tempTransferFile, cb=pp.updateProgress, num_cb=size/_TRANSFER_CHUNK_SIZE)
            pp.done += size
            move(tempTransferFile, objPath)
            copyfile(objPath, filePath)
    else:
        print len(fitTrackedData), 'items being tracked'
        print (len(need)+len(missing)), 'needed items missing in local cache'
        print len(missing), 'items missing locally AND remotely (no way to retrieve these)'
        print '%.2fMB needs to be downloaded'%(totalSize/1048576)

def put(fitTrackedData, opts):
    have = []
    missing = []
    
    bucket = _getBucket()
    
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        objPre, objSuf = objHash[:2], objHash[2:]
        objPath = path.join(cacheDir, objPre, objSuf)
        
        keyName = '%s/%s'%(objPre, objSuf)
        key = bucket.get_key(keyName)
        
        key or path.exists(objPath) and have.append((keyName, objPath, size)) or missing.append(filePath)

    totalSize = sum([size for f,k,o,size in have])

    if opts['transfer']:
        pp = _ProgressPrinter(totalSize)
        
        for keyName,objPath,size in have:
            pp.itemName = filePath
            
            # S3 uploads are atomic. So if a file upload is interrupted, it will be as if none of
            # it was uploaded at all. So transient temporary transfer location is not needed as
            # it is for downloading from S3
            key = bucket.new_key(key_name = keyName)
            key.set_contents_from_filename(objPath, cb=pp.updateProgress, num_cb=size/_TRANSFER_CHUNK_SIZE)
            pp.done += size
    else:
        print len(fitTrackedData), 'items being tracked'
        print (len(have)+len(missing)), 'new items missing in remote location'
        print len(missing), 'items missing locally AND remotely (no way to retrieve these)'
        print '%.2fMB needs to be uploaded'%(totalSize/1048576)

