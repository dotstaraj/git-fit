from . import gitDirOperation, refreshStats, getFitSize, readFitFile, writeFitFile, getCommitFile
from . import repoDir, fitDir, cacheDir, tempDir, readCacheFile, writeCacheFile, commitsDir
from paths import getValidFitPaths
from subprocess import Popen as popen, PIPE
from os.path import dirname, basename, exists, join as joinpath, getsize
from os import walk, makedirs, remove, close as osclose
from shutil import copyfile, move
from sys import stdout
from tempfile import mkstemp

def getDataStore(progressCallback):
    moduleName = popen('git config fit.datastore.moduleName'.split(), stdout=PIPE).communicate()[0].strip()
    modulePath = popen('git config fit.datastore.modulePath'.split(), stdout=PIPE).communicate()[0].strip()

    if not moduleName:
        raise Exception('error: No external data store is configured. Check the fit.datastore keys in git config.')

    if modulePath:
        import sys
        sys.path.append(modulePath)

    try:
        from importlib import import_module
        return import_module(moduleName).Store(progressCallback)
    except Exception as e:
        print 'error: Could not load the data store configured in fit.datastore.'
        raise

@gitDirOperation(repoDir)
def findObject(obj):
    path = joinpath(cacheDir, joinpath(obj[:2], obj[2:]))
    return path if exists(path) else None

@gitDirOperation(repoDir)
def placeObjects(objects, progressCallback=lambda x: None):
    for i, (obj, src) in enumerate(objects):
        dst = joinpath(cacheDir, joinpath(obj[:2], obj[2:]))
        if not exists(dst):
            popen(('mkdir -p %s'%dirname(dst)).split()).wait()
            popen(('cp %s %s'%(src, dst)).split()).wait()
        
        progressCallback(i)

@gitDirOperation(repoDir)
def removeObjects(objects):
    for obj in objects:
        path = joinpath(cacheDir, joinpath(obj[:2], obj[2:]))
        if exists(path):
            remove(path)

@gitDirOperation(repoDir)
def getUpstreamItems(fitTrackedData, paths):
    return set(readFitFile(getCommitFile()))

@gitDirOperation(repoDir)
def getDownstreamItems(fitTrackedData, paths, stats):
    return [p for p in paths if p in stats and stats[p][0] == 0 and not findObject(fitTrackedData[p][0])]

def getCacheSize(lru):
    return sum([sum([o[1] for o in e]) for e in lru])

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

def get(fitTrackedData, pathArgs=None, summary=False, showlist=False, quiet=False):    
    allItems = fitTrackedData.keys()
    validPaths = getValidFitPaths(pathArgs, allItems, repoDir) if pathArgs else allItems

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
                key = joinpath(objHash[:2], objHash[2:])
                needed.append((filePath, key, objHash, objPath, size))

    totalSize = sum([size for f,k,h,p,size in needed])

    if len(needed) == 0:
        print 'No tranfers needed! %s items retrieved from cache and the rest already exist.'%len(touched)
    elif showlist:
        print
        for filePath,k,h,p,size in needed:
            print '  %6.2fMB  %s'%(size/1048576, filePath)
        print '\nThe above objects can be tranferred (total transfer size: %.2fMB).'%(totalSize/1048576)
        print 'You may run git-fit get to start the transfer.'
    elif summary:
        print len(validPaths), 'items are being tracked'
        print len(needed), 'of the tracked items are not cached locally (need to be downloaded)'
        print '%.2fMB in total can be downloaded'%(totalSize/1048576)
        print 'Run \'git-fit get -l\' to list these items.'
    else:
        pp = _QuietProgressPrinter() if quiet else _ProgressPrinter()
        pp.setTotalSize(totalSize)
        store = getDataStore(pp.updateProgress)
        errors = []
        objects = []
        needed.sort()
        if not exists(tempDir):
            popen(['mkdir', '-p', tempDir]).wait()
        for filePath,key,objHash,objPath,size in needed:
            pp.newItem(filePath, size)
            
            # Copy download to temp file first, and then to actual object location
            # This is to prevent interrupted downloads from causing bad objects to be placed
            # in the objects cache
            (tempHandle, tempTransferFile) = mkstemp(dir=tempDir)
            osclose(tempHandle)
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
                objects.append((objHash, size))
            else:
                pp.updateProgress(size, size, custom_item_string='ERROR')
                errors.append(filePath)

        pp.done()
        store.close()
        print
        updateCacheFile(objects, fitTrackedData)

        if len(errors) > 0:
            print 'Some items could not be transferred:'
            print '\n'.join(errors)
            print 'Above items could not be transferred:'

    refreshStats(touched)

def put(fitTrackedData, pathArgs=None, force=False, summary=False,  showlist=False, quiet=False):
    commitsFile = getCommitFile()
    commitsFitData = readFitFile(commitsFile)
    available = []
    for filePath,(objHash, size) in commitsFitData.iteritems():
        key = joinpath(objHash[:2], objHash[2:])
        objPath = findObject(objHash)
        available.append((filePath, key, objHash, objPath, size))

    totalSize = sum([size for f,k,h,p,size in available])

    if len(available) == 0:
        print 'No tranfers needed! There are no cached objects to put in external location for HEAD.'
    elif showlist:
        print
        for filePath,k,h,p,size in available:
            print '  %6.2fMB  %s'%(size/1048576, filePath)
        print '\nThe above objects can be tranferred (maximum total transfer size: %.2fMB).'%(totalSize/1048576)
        print 'You may run git-fit put to start the transfer.'
    elif summary:
        print len(fitTrackedData), 'items are being tracked'
        print len(available), 'of the tracked items MAY need to be sent to external location'
        print '%.2fMB maximum possible transfer size'%(totalSize/1048576)
        print 'Run \'git-fit put -l\' to list these items.'
    else:
        pp = _QuietProgressPrinter() if quiet else _ProgressPrinter()
        pp.setTotalSize(totalSize)
        store = getDataStore(pp.updateProgress)
        errors = []
        objects = []
        available.sort()
        for filePath,keyName,objHash,objPath,size in available:
            pp.newItem(filePath, size)
            if not exists(objPath):
                pp.updateProgress(size, size, custom_item_string='ERROR')
                errors.append(filePath)
                continue

            done = True
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
                    done = False
                    pp.updateProgress(size, size, custom_item_string='ERROR')
                    errors.append(filePath)
            if done:
                del commitsFitData[filePath]
                objects.append((objHash, size))

        pp.done()
        store.close()
        print
        updateCacheFile(objects, fitTrackedData)
        if len(commitsFitData) > 0:
            writeFitFile(commitsFitData, commitsFile)
        else:
            remove(commitsFile)

        if len(errors) > 0:
            print '\nSome items could not be transferred:'
            print '\n'.join(errors)
            print '\nAbove items could not be transferred:'

def updateCacheFile(objects, fitTrackedData):
    lru = readCacheFile()
    # lru is a queue, so append most recent to end of list
    lru.append(objects)

    fitSize = getFitSize(fitTrackedData)
    cacheSize = getCacheSize(lru)
    if cacheSize > fitSize * 2:
        print 'Cache size (%.2fMB) is larger than twice the tracked size (%.2fMB).'%(cacheSize/1048576., fitSize/1048576.)
        print '\tPruning will occur.'
    else:
        print 'Cache size is %.2fMB and tracked size is %.2fMB (will not prune at this time).'%(cacheSize/1048576., fitSize/1048576.)

    # objects being added to this commit might already exist
    # in cache as part of other commit, so for each lru entry,
    # clear the objects list and recreate it
    print 'Updating cache file...',
    objRevMap = {}
    for i, objList in enumerate(lru):
        lru[i] = []
        for o,s in objList:
            objRevMap[(o,s)] = i

    for o,i in objRevMap.iteritems():
        lru[i].append(o)

    # keep cache size less than twice the size of fit-tracked data
    if cacheSize > fitSize * 2:
        print '\nPruning cache...',
        while cacheSize > fitSize * 2:
            if len(lru) == 0:
                break
            objects = lru.pop(0)
            if len(objects) == 0:
                continue
            objects, sizes = zip(*objects)
            removeObjects(objects)
            cacheSize -= sum(sizes)

    writeCacheFile(lru)
    print 'Done.'
