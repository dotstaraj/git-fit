from fit import gitDirOperation, refreshStats, getFitSize, getHeadRevision
from fit import repoDir, fitDir, cacheDir, syncDir, tempDir, cacheLruFile
from paths import getValidFitPaths
from subprocess import Popen as popen
from os.path import dirname, basename, exists, join as joinpath, getsize
from os import walk, makedirs, remove
from shutil import copyfile, move
from sys import stdout
from tempfile import mkstemp

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
def getObjectInfo(objName):
    obj = joinpath(objName[:2], objName[2:])
    return obj, joinpath(cacheDir, obj), joinpath(syncDir, obj)

@gitDirOperation(repoDir)
def findObject(objName):
    obj, objInCache, objToSync = getObjectInfo(objName)
    if exists(objToSync):
        return objToSync
    elif exists(objInCache):
        return objInCache
    else:
        return None

@gitDirOperation(repoDir)
def placeObject(objName, source):
    obj, objInCache, objToSync = getObjectInfo(objName)

    if not (exists(objInCache) or exists(objToSync)):
        popen(('mkdir -p %s'%dirname(objToSync)).split()).wait()
        popen(('cp %s %s'%(source, objToSync)).split()).wait()

@gitDirOperation(repoDir)
def removeObject(objName):
    objPath = findObject(objName)
    if objPath:
        remove(objPath)


@gitDirOperation(repoDir)
def getCacheObjectPaths():
    paths = []

    cacheIter = walk(cacheDir)

    root, dirs, files = cacheIter.next()
    if basename(syncDir) in dirs:
        dirs.remove(basename(syncDir))

    for root, dirs, files in cacheIter:
        for f in files:
            paths.append(joinpath(root,f))
    
    return paths

@gitDirOperation(repoDir)
def getUpstreamItems(fitTrackedData, paths):
    objects = []
    hashToPathFitData = {fitTrackedData[p][0]:p for p in paths}

    for root, dirs, files in walk(syncDir):
        for f in files:
            objPath = joinpath(root,f)
            o = basename(root)+f
            if o in hashToPathFitData:
                objects.append(hashToPathFitData[o])
    
    return objects

@gitDirOperation(repoDir)
def getDownstreamItems(fitTrackedData, paths):
    return [p for p in paths if exists(p) and getsize(p) == 0 and findObject(fitTrackedData[p][0])]

@gitDirOperation(repoDir)
def getCacheSize():
    return sum(getsize(o) for o in getCacheObjectPaths())

class _ProgressPrinter:
    def __init__(self):
        self.size_total = 0
        self.size_item = 0
        self.size_done = 0
        self.item_name = ''
        self.item_started = False

    def updateProgress(self, done, size, custom_item_string=None):
        if custom_item_string:
            fmt_args = (
                (self.size_done+done)*100./self.size_total,
                custom_item_string,
                self.item_name
            )
            print '\rOverall: %6.2f%%    %s   %s'%fmt_args,
        else:
            fmt_args = (
                (self.size_done+done)*100./self.size_total,
                self.size_item/1048576.,
                done*100./size,
                self.item_name
            )
            print '\rOverall: %6.2f%%    %7.3f MB   %6.2f%%   %s'%fmt_args,
        stdout.flush()
        self.item_started = True
    def newItem(self, name, size):
        if self.size_item and self.item_started:
            print

        self.size_done += self.size_item
        self.item_name = name
        self.size_item = size
        self.item_started = False

    def done(self):
        if self.size_item > 0:
            self.size_done += self.size_item
            print

    def setTotalSize(self, totalSize):
        self.size_total = totalSize

class _QuietProgressPrinter:
    def updateProgress(self, done, size):
        pass
    def newItem(self, name, size):
        pass
    def done(self):
        pass
    def setTotalSize(self, totalSize):
        pass

def get(fitTrackedData, pathArgs=None, summary=False, verbose=False, quiet=False):
    global _fitstore
    
    allItems = fitTrackedData.keys()
    validPaths = getValidFitPaths(pathArgs, allItems, repoDir) if pathArgs else allItems
    if len(fitTrackedData) == 0 or len(validPaths) == 0:
        return

    pp = _QuietProgressPrinter() if quiet else _ProgressPrinter()

    needed = []   # not in working tree nor in cache, must be downloaded
    touched = {}
    
    for filePath in validPaths:
        objHash, size = fitTrackedData[filePath]
        if exists(filePath) and getsize(filePath) == 0:
            objPath = findObject(objHash)
            fileDir = dirname(filePath)
            fileDir and (exists(fileDir) or makedirs(fileDir))
            if objPath:
                copyfile(objPath, filePath)
                touched[filePath] = objHash
            else:
                obj, objInCache, objToSync = getObjectInfo(objHash)
                needed.append((filePath, obj, objHash, objInCache, size))

    totalSize = sum([size for f,k,h,o,size in needed])
    pp.setTotalSize(totalSize)

    if len(needed) == 0:
        print 'No tranfers needed! Working copy has been populated with all', len(fitTrackedData), 'tracked items.'
    elif verbose:
        print
        for filePath,key,objHash,objPath,size in needed:
            print '  %.2fMB  %s'%(size/1048576, filePath)
        print '\nThe above objects can be tranferred. Total transfer size: %.2fMB'%(totalSize/1048576)
    elif summary:
        print len(validPaths), 'items are being tracked'
        print len(needed), 'of the tracked items are not cached locally (need to be downloaded)'
        print '%.2fMB in total can be downloaded'%(totalSize/1048576)
        print 'Run \'git-fit get -v\' to list these items.'
    else:
        try:
            store = _fitstore.Store(pp.updateProgress)
        except Exception as e:
            print e
            return
        errors = []
        objects = []
        needed.sort()
        for filePath,key,objHash,objPath,size in needed:
            pp.newItem(filePath, size)
            
            # Copy download to temp file first, and then to actual object location
            # This is to prevent interrupted downloads from causing bad objects to be placed
            # in the objects cache
            (tempHandle, tempTransferFile) = mkstemp(dir=tempDir)
            tempHandle.close()
            key = store.check(key)

            try:
                transferred = store.get(key, tempTransferFile, size)
            except:
                transferred = False
            if key and transferred:
                pp.updateProgress(size, size)
                popen(['mkdir', '-p', dirname(objPath)]).wait()
                popen(['mv', tempTransferFile, objPath]).wait()
                popen(['cp', objPath, filePath]).wait()
                touched[filePath] = objHash
                objects.append((basename(dirname(objPath))+basename(objPath), size))
            else:
                errors.append(filePath)

        pp.done()
        store.close()
        updateCacheFile(objects)

        if len(errors) > 0:
            print 'Some items could not be transferred:'
            print '\n'.join(errors)
            print 'Above items could not be transferred:'

    refreshStats(touched)

def put(fitTrackedData, summary=False,  verbose=False, quiet=False):
    global _fitstore
    
    if len(fitTrackedData) == 0:
        return

    pp = _QuietProgressPrinter() if quiet else _ProgressPrinter()

    available = []   # not in external location, must be uploaded
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        obj, objInCache, objToSync = getObjectInfo(objHash)
        objPath = findObject(objHash)

        if objPath == objToSync:
            available.append((filePath, obj, objPath, objInCache, size))

    totalSize = sum([size for f,k,o,c,size in available])
    pp.setTotalSize(totalSize)

    if len(available) == 0:
        print 'No tranfers needed! There are no objects to put in external location for HEAD.'
    elif verbose:
        print
        for filePath,keyName,objPath,objInCache,size in available:
            print '  %.2fMB  %s'%(size/1048576, filePath)
        print '\nThe above objects may need to be tranferred. Total transfer size: %.2fMB'%(totalSize/1048576)
    elif summary:
        print len(fitTrackedData), 'items are being tracked'
        print len(available), 'of the tracked items MAY need to be sent to external location'
        print '%.2fMB maximum possible transfer size'%(totalSize/1048576)
        print 'Run \'git-fit put -v\' to list these items.'
    else:
        try:
            store = _fitstore.Store(pp.updateProgress if not quiet else lambda a,b:None)
        except Exception as e:
            print e
            return
        errors = []
        objects = []
        available.sort()
        for filePath,keyName,objPath,objInCache,size in available:
            pp.newItem(filePath, size)
            if exists(objPath):
                move = True
                if store.check(keyName):
                    pp.updateProgress(size, size, custom_item_string='NO TRANSFER NEEDED')
                else:
                    try:
                        transferred = store.put(objPath, keyName, size)
                    except:
                        transferred = False
                    if transferred:
                        pp.updateProgress(size, size)
                    else:
                        move = False
                        errors.append(filePath)
                if move:
                    popen(['mkdir', '-p', dirname(objInCache)]).wait()
                    popen(['mv', objPath, objInCache]).wait()
                    objects.append((basename(dirname(objInCache))+basename(objInCache), size))
            elif not exists(objInCache):
                errors.append(filePath)
            else:
                pp.updateProgress(size, size, custom_item_string='NO TRANSFER NEEDED')

        pp.done()
        store.close()
        updateCacheFile(objects)

        if len(errors) > 0:
            print '\nSome items could not be transferred:'
            print '\n'.join(errors)
            print '\nAbove items could not be transferred:'

def updateCacheFile(objects):
    lru = readCacheFile()
    headRev = getHeadRevision()

    fitSize = getFitSize(fitTrackedData)
    cacheSize = getCacheSize()
    if cacheSize > fitSize * 2:
        print 'Cache size (%.2fMB) is larger than twice the tracked size (%.2fMB).'%(cacheSize/1048576., fitSize/1048576.)
        print '\tPruning will occur.'
    else:
        print 'Cache size is (%.2fMB) and tracked size is (%.2fMB).'%(cacheSize/1048576., fitSize/1048576.)

    # lru is a queue, so append most recent to end of list
    lru.append([headRev, objects])

    # objects being added to this commit might already exist
    # in cache as part of other commit, so for each lru entry,
    # clear the objects list and recreate it
    print '\tUpdating cache file...'
    objRevMap = {}
    for i, (rev, objList) in enumerate(lru):
        lru[i][1] = []
        for o,s in objList:
            objRevMap[(o,s)] = i

    for o,i in objRevMap.iteritems():
        lru[i][1].append(o)

    # keep cache size less than twice the size of fit-tracked data
    if cacheSize > fitSize * 2:
        print '\tPruning cache...'
        while cacheSize > fitSize * 2:
            rev, objects = lru.pop(0)
            for o, s in objects:
                removeObject(o)
                cacheSize -= s

    writeCacheFile(lru)
    print '\tDone.'
