from fit import gitDirOperation, repoDir, fitDir, cacheDir, syncDir, getChangedItems
from subprocess import Popen as popen
from os.path import dirname, basename, exists, join as joinpath, getsize
from os import walk
from shutil import copyfile, move
from sys import stdout


_fitstore = None
def loadstore():
    global _fitstore
    import s3store
    import localstore
    _fitstore = s3store

class Store:
    def __init__(self, progress):
        pass
    def check(self, dst):
        return None
    def get(self, src, dst, size):
        return False
    def put(self, src, dst, size):
        return False
    def close(self):
        pass

@gitDirOperation(repoDir)
def _getObjectInfo(objName):
    obj = joinpath(objName[:2], objName[2:])
    return obj, joinpath(cacheDir, obj), joinpath(syncDir, obj)

@gitDirOperation(repoDir)
def findObject(objName):
    obj, objInCache, objToSync = _getObjectInfo(objName)
    if exists(objToSync):
        return objToSync
    elif exists(objInCache):
        return objInCache
    else:
        return None

@gitDirOperation(repoDir)
def placeObject(objName, source):
    obj, objInCache, objToSync = _getObjectInfo(objName)

    if not (exists(objInCache) or exists(objToSync)):
        popen(('mkdir -p %s'%dirname(objToSync)).split()).wait()
        popen(('cp %s %s'%(source, objToSync)).split())

@gitDirOperation(repoDir)
def getUnsyncedObjects():
    objects = {}

    for root, dirs, files in walk(syncDir):
        for f in files:
            objPath = joinpath(root,f)
            objects[basename(dirname(objPath))+basename(objPath)] = objPath
    
    return objects

class _ProgressPrinter:
    def __init__(self):
        self.size_total = 0
        self.size_item = 0
        self.size_done = 0
        self.item_name = ''

    def updateProgress(self, done, size):
        fmt_args = (
                self.item_name,
                self.size_item/1048576.,
                done*100./size,
                (self.size_done+done)*100./self.size_total
        )
        print '\r%s:    %7.3f MB    %6.2f%%       Overall: %6.2f%%'%fmt_args,
        stdout.flush()
    def newItem(self, name, size):
        if self.size_item:
            print# ('\r%s: Done!'+(' '*50))%self.item_name

        self.size_done += self.size_item
        self.item_name = name
        self.size_item = size

    def done(self):
        if self.size_item > 0:
            print

    def setTotalSize(self, totalSize):
        self.size_total = totalSize

def get(fitTrackedData, paths, transfer=False):
    global _fitstore
    needed = []   # not in working tree nor in cache, must be downloaded
    missing = []  # not in working tree, cache, OR external location!
    
    if len(fitTrackedData) == 0 or len(paths) == 0:
        return

    pp = _ProgressPrinter()
    store = _fitstore.Store(pp.updateProgress)
    
    for filePath in paths:
        objHash, size = fitTrackedData[filePath]
        if exists(filePath) and getsize(filePath) == 0:
            objPath = findObject(objHash)
            
            if objPath:
                copyfile(objPath, filePath)
            else:
                key = store.check(_getObjectInfo(objHash)[0])
                if key:
                    needed.append((filePath, key, _getObjectInfo(objHash)[1], size))
                else:
                    missing.append(filePath)

    totalSize = sum([size for f,k,o,size in needed])
    pp.setTotalSize(totalSize)

    if transfer:
        errors = []
        for filePath,key,objPath,size in needed:
            pp.newItem(filePath, size)
            
            # Copy download to temp file first, and then to actual object location
            # This is to prevent interrupted downloads from causing bad objects to be placed
            # in the objects cache
            tempTransferFile = joinpath(fitDir, '.tempTransfer')
            if store.get(key, tempTransferFile, size):
                popen(['mkdir', '-p', dirname(objPath)])
                popen(['mv', tempTransferFile, objPath])
                popen(['cp', objPath, filePath])
            else:
                errors.append(filePath)
        pp.done()
        if len(needed) > 0 and len(errors) < len(needed):
            print 'refreshing'
            getChangedItems(fitTrackedData)  # just refresh file stats

        if len(errors) > 0:
            print 'Some items could not be transferred:'
            print '\n'.join(errors)
            print 'Above items could not be transferred:'
    else:
        if len(needed) or len(missing):
            print len(fitTrackedData), 'items are being tracked'
            print (len(needed)+len(missing)), 'of the tracked items are not cached locally (need to be downloaded)'
            if len(missing):
                print len(missing), 'of those items were NOT found in external location (no way to retrieve these!)'
            print '%.2fMB in total can be downloaded'%(totalSize/1048576)
        else:
            print 'No tranfers needed! Working copy has been populated with all', len(fitTrackedData), 'tracked items.'

    store.close()

def put(fitTrackedData, transfer=False):
    global _fitstore
    available = []   # not in external location, must be uploaded
    missing = []     # not in external location, cache, OR working copy!
    
    if len(fitTrackedData) == 0:
        return

    pp = _ProgressPrinter()
    store = _fitstore.Store(pp.updateProgress)
    
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        obj, objInCache, objToSync = _getObjectInfo(objHash)
        objPath = findObject(objHash)
        if store.check(obj):
            if objPath == objToSync:
                popen(['mkdir', '-p', dirname(objInCache)])
                popen(['mv', objPath, objInCache])
        else:
            if objPath:
                available.append((filePath, obj, objPath, objInCache, size))
            else:
                missing.append(filePath)

    totalSize = sum([size for f,k,o,c,size in available])
    pp.setTotalSize(totalSize)

    if transfer:
        errors = []      
        for filePath,keyName,objPath,objInCache,size in available:
            pp.newItem(filePath, size)
            if store.put(objPath, keyName, size):
                if objPath != objInCache:
                    popen(['mkdir', '-p', dirname(objInCache)])
                    popen(['mv', objPath, objInCache])
            else:
                errors.append(filePath)

        pp.done()
        if len(errors) > 0:
            print '\nSome items could not be transferred:'
            print '\n'.join(errors)
            print '\nAbove items could not be transferred:'
    else:
        if len(available)+len(missing) > 0:
            print len(fitTrackedData), 'items are being tracked'
            print (len(available)+len(missing)), 'of the tracked items have not been sent to external location (need to be uploaded)'
            if len(missing) > 0:
                print len(missing), 'items missing locally AND remotely (no way to retrieve these)'
            print '%.2fMB needs to be uploaded'%(totalSize/1048576)
        else:
            print 'No tranfers needed! There are no objects to put in external location for HEAD commit.'

    store.close()

