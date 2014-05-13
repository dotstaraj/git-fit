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
        popen(('cp %s %s'%(source, objToSync)).split()).wait()

@gitDirOperation(repoDir)
def getUnsyncedObjects():
    objects = []

    for root, dirs, files in walk(syncDir):
        for f in files:
            objPath = joinpath(root,f)
            objects.append(basename(dirname(objPath))+basename(objPath))
    
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

def get(fitTrackedData, paths, summary=False):
    global _fitstore
    needed = []   # not in working tree nor in cache, must be downloaded
    
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
                obj, objInCache, objToSync = _getObjectInfo(objHash)
                needed.append((filePath, obj, objInCache, size))

    totalSize = sum([size for f,k,o,size in needed])
    pp.setTotalSize(totalSize)

    if summary:
        if len(needed):
            print len(fitTrackedData), 'items are being tracked'
            print len(needed), 'of the tracked items are not cached locally (need to be downloaded)'
            print '%.2fMB in total can be downloaded'%(totalSize/1048576)
        else:
            print 'No tranfers needed! Working copy has been populated with all', len(fitTrackedData), 'tracked items.'
    else:
        errors = []
        for filePath,key,objPath,size in needed:
            pp.newItem(filePath, size)
            
            # Copy download to temp file first, and then to actual object location
            # This is to prevent interrupted downloads from causing bad objects to be placed
            # in the objects cache
            tempTransferFile = joinpath(fitDir, '.tempTransfer')
            key = store.check(key)
            if key and store.get(key, tempTransferFile, size):
                popen(['mkdir', '-p', dirname(objPath)]).wait()
                popen(['mv', tempTransferFile, objPath]).wait()
                popen(['cp', objPath, filePath]).wait()
            else:
                errors.append(filePath)
        pp.done()

        if len(errors) > 0:
            print 'Some items could not be transferred:'
            print '\n'.join(errors)
            print 'Above items could not be transferred:'


    store.close()

def put(fitTrackedData, summary=False):
    global _fitstore
    available = []   # not in external location, must be uploaded
    
    if len(fitTrackedData) == 0:
        return

    pp = _ProgressPrinter()
    store = _fitstore.Store(pp.updateProgress)
    
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        obj, objInCache, objToSync = _getObjectInfo(objHash)
        objPath = findObject(objHash)

        if objPath == objToSync:
            available.append((filePath, obj, objPath, objInCache, size))

    totalSize = sum([size for f,k,o,c,size in available])
    pp.setTotalSize(totalSize)

    if summary:

        if len(available)> 0:
            print len(fitTrackedData), 'items are being tracked'
            print len(available), 'of the tracked items MAY need to be sent to external location'
            print '%.2fMB maximum possible transfer size'%(totalSize/1048576)
        else:
            print 'No tranfers needed! There are no objects to put in external location for HEAD commit.'
    else:
        errors = []      
        for filePath,keyName,objPath,objInCache,size in available:
            pp.newItem(filePath, size)
            if exists(objPath):
                move = True
                if store.check(keyName):
                    pp.updateProgress(size, size)
                elif not store.put(objPath, keyName, size):
                    move = False
                    errors.append(filePath)
                if move:
                    popen(['mkdir', '-p', dirname(objInCache)]).wait()
                    popen(['mv', objPath, objInCache]).wait()
            elif not exists(objInCache):
                errors.append(filePath)
            else:
                pp.updateProgress(size, size)

        pp.done()
        if len(errors) > 0:
            print '\nSome items could not be transferred:'
            print '\n'.join(errors)
            print '\nAbove items could not be transferred:'

    store.close()

