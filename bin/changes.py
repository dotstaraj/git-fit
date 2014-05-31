from fit import fitStats, gitDirOperation, repoDir
from fit import readStatFile, writeStatFile, refreshStats
from objects import findObject, getObjectInfo
from paths import getValidFitPaths
import merge
from subprocess import Popen as popen, PIPE
from os.path import exists, dirname, getsize
from os import remove, makedirs
from shutil import copyfile
from itertools import chain

'''
parser.add_argument('-a', '--all', action='store_true', help='List all unchanged items in addition to the changed ones')
'''

def printLegend():
    print 'Meaning of status symbols:'
    print '-------------------------------------------------------------------------------'
    print '*   modified'
    print '+   new/added (fit will start tracking upon commit)'
    print '-   removed (physically deleted, fit will discontinue tracking it upon commit)'
    print '~   untracked (marked by you to be ignored by fit, fit will discontinue tracking it upon commit)'
    print
    print 'F  an item fit is already tracking, but is also currently staged for commit in git'
    print 'B  a binary file staged for commit in git that fit has not been told to ignore'
    print '-------------------------------------------------------------------------------'
    print

def printStatus(fitTrackedData, pathArgs=None, legend=True):
    if legend:
        printLegend()

    trackedItems = getTrackedItems()
    paths = getValidFitPaths(pathArgs, trackedItems.union(fitTrackedData))
    modified, added, removed, untracked = getChangedItems(fitTrackedData, trackedItems, paths)
    conflict, binary = getStagedOffenders()

    if not paths:
        paths = fitTrackedData.keys()

    paths = {p:findObject(fitTrackedData[p][0]) for p in paths}
    toupload = {p for p,o in paths.iteritems() if o == getObjectInfo(fitTrackedData[p][0])[2]}
    todownload = {p for p,o in paths.iteritems() if exists(p) and getsize(p) == 0 and not o}

    offenders = set(chain(conflict, binary))

    modified =  [('*  ', i) for i in set(modified)-offenders]
    added =     [('+  ', i) for i in set(added)-offenders]
    removed =   [('-  ', i) for i in removed]
    untracked = [('~  ', i) for i in set(untracked)-offenders]
    conflict =  [('F  ', i) for i in conflict]
    binary =    [('B  ', i) for i in binary]

    if all(len(l) == 0 for l in [added,removed,untracked,modified,conflict,binary,toupload,todownload]):
        print 'Nothing to show (no problems or changes detected).'
        return

    print
    for c,f in sorted(untracked+modified+added+removed+conflict+binary, key=lambda i: i[1]):
        print '  ', c, f
    print

    if len(toupload) > 0:
        print 'Items TO UPLOAD:'
        print '  %s objects in HEAD have not been synced and may need to be uploaded.'%len(toupload)
        print '  Run git fit --put -s to see what they are, or git fit --put to start'
        print '  uploading them if needed.'
    if len(todownload) > 0:
        print 'Items TO DOWNLOAD:'
        print '  %d objects in HEAD are not in the local cache and need to be downloaded.'%len(todownload)
        print '  Run git fit --get -s to see what they are, or git fit --get [<paths>] to start'
        print '  downloading them if needed.'


# Returns a dictionary of modified items, mapping filename to (hash, filesize).
# Uses cached stats as the primary check to detect unchanged files, and only then
# does checksum comparisons if needed (just like git does)
def getModifiedItems(existingItems, fitTrackedData):
    if len(existingItems) == 0:
        return {}

    # get current stats info of all existing items
    statsNew = {f: fitStats(f) for f in existingItems}

    # The stat file is a Python-pickled dictionary of the following form:
    #   {filename --> (st_size, st_mtime, st_ctime, st_ino, checksum_hash)}
    #
    statsOld = readStatFile()

    # An item is "touched" if its cached stats don't match its new stats.
    # "Touched" is a necessary but not sufficient condition for an item to
    # be considered "modified". Modified items are those that are touched
    # AND whose checksums are different, so we do checksum comparisons next
    touchedItems = [f for f in statsNew if statsNew[f][0] > 0 and (f not in statsOld or tuple(statsOld[f][1]) != statsNew[f])]

    # Basically the next two lines make "touchedItems" a dictionary mapping filenames to their hash sums.
    # Hashes are re-computed ONLY for touched items.
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    touchedItems = dict(zip(touchedItems, p.communicate('\n'.join(touchedItems))[0].strip().split('\n')))

    # Check all existing items for modification by comparing their expected
    # hash sums (those stored in the .fit file) to their new, actual hash sums.
    # The new hash sums come from either the touched items determined above, or,
    # if not touched, from cached hash values computed from a previous run of this
    # same code
    modifiedItems = {}
    for i in existingItems:  # loop "existing" instead of touched items to update cached stats
                             # for everything, not just touched items
        trackedHash = fitTrackedData[i][0]
        size = statsNew[i][0]
        if i in touchedItems and touchedItems[i] != trackedHash:
            modifiedItems[i] = (touchedItems[i], size)
        elif size > 0 and i in statsOld and statsOld[i][0] != trackedHash:
            modifiedItems[i] = (statsOld[i][0], size)

    # Update our cached stats if necessary
    writeStatCache = False
    if len(touchedItems) > 0:
        writeStatCache = True
        for f in touchedItems:
            statsOld[f] = (touchedItems[f], statsNew[f])

    # By this point we should have new stats for all existing items, stored in
    # "statsOld". If we don't, it means some items have been deleted and can
    # be removed from the cached stats
    if len(existingItems) != len(statsOld):
        writeStatCache = True
        for f in statsOld.keys():
            if f not in existingItems:
                del statsOld[f]

    if writeStatCache:
        writeStatFile(statsOld)

    return modifiedItems

# From all existing physical files under repo directory NOT tracked by
# git, get those that fit is being asked to track, as indicated by current
# state of set/unset "fit" attributes.
@gitDirOperation(repoDir)
def getTrackedItems():
    p = popen('git ls-files -o'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    return {l[:-11] for l in p.stdout if l.endswith(' set\n')}

@gitDirOperation(repoDir)
def getChangedItems(fitTrackedData, trackedItems, requestedItems=None):

    # These are the items fit is currently tracking
    expectedItems = set(fitTrackedData)

    if requestedItems:
        expectedItems &= requestedItems
        trackedItems &= requestedItems

    # Use set difference and intersection to determine some info about changes
    # to the status of our items
    existingItems = expectedItems & trackedItems
    newItems = trackedItems - expectedItems
    missingItems = expectedItems - trackedItems

    # An item could be in missingItems for one of two reasons: either it
    # has been deleted from the working directory, or it has been marked
    # to not be tracked by fit anymore. We separate out these two sets
    # of missing items:
    untrackedItems = {i for i in missingItems if exists(i)}
    removedItems = missingItems - untrackedItems

    # From the existing items, we're interested in only the modified ones
    modifiedItems = getModifiedItems(existingItems, fitTrackedData)

    return (modifiedItems, newItems, removedItems, untrackedItems)

def _filterBinaryFiles(files):
    binaryFiles = []

    p = popen('file -f -'.split(), stdout=PIPE, stdin=PIPE)
    fileTypes = p.communicate('\n'.join(files))[0].strip().split('\n')

    for f in fileTypes:
        sepIdx = f.find(':')
        filepath = f[:sepIdx]
        if f.find('text', sepIdx) < 0:
            binaryFiles.append(filepath)

    return binaryFiles

@gitDirOperation(repoDir)
def getStagedOffenders():
    fitConflict = []
    binaryFiles = []

    staged = []
    p = popen('git diff --name-only --diff-filter=A --cached'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    for l in p.stdout:
        filepath = l[:l.find(':')]
        if l.endswith(' set\n'):
            fitConflict.append(filepath)
        elif l.endswith(' unspecified\n'):
            staged.append(filepath)

    if len(staged) > 0:
        binaryFiles = _filterBinaryFiles(staged)

    return fitConflict, binaryFiles

@gitDirOperation(repoDir)
def restore(fitTrackedData, pathArgs=None):
    trackedItems = getTrackedItems()
    paths = getValidFitPaths(pathArgs, trackedItems.union(fitTrackedData))
    modified, added, removed, untracked = getChangedItems(fitTrackedData, trackedItems, paths)

    for i in sorted(added):
        remove(i)
        print 'Removed: %s'%i

    missing = 0
    touched = {}

    result = _restoreItems('Added', sorted(removed), fitTrackedData)
    missing += result[0]
    touched.update(result[1])
    result = _restoreItems('Replaced', sorted(modified), fitTrackedData)
    missing += result[0]
    touched.update(result[1])

    print

    refreshStats(touched)

    if missing > 0:
        print 'For %d of the fit objects just restored, only empty stub files were'%missing
        print 'created in their stead. This is because those objects are not cached and must be'
        print 'downloaded. To start this download, run "git fit --get" with the same path arguments'
        print 'passed to --restore (if any).\n'

def _restoreItems(restoreType, objects, fitTrackedData):
    missing = 0
    touched = {}
    for filePath in objects:
        objHash = fitTrackedData[filePath][0]
        objPath = findObject(objHash)
        fileDir = dirname(filePath)
        fileDir and (exists(fileDir) or makedirs(fileDir))
        if objPath:
            print '%s: %s'%(restoreType, filePath)
            copyfile(objPath, filePath)
            touched[filePath] = objHash
        else:
            print '%s (empty): %s'%(restoreType, filePath)
            open(filePath, 'w').close()  #write a 0-byte file as placeholder
            missing += 1

    return (missing, touched)

@gitDirOperation(repoDir)
def save(fitTrackedData, pathArgs=None):
    if merge.isMergeInProgress():
        if pathArgs:
            print 'A .fit merge is currently in progress and unresolved. Path arguments to --save'
            print 'cannot be given. If you have finished making selections in FIT_MERGE, run'
            print 'git fit --save without any arguments to complete conflict resolution.'
            return
        _saveItems(fitTrackedData, paths=merge.resolve(fitTrackedData))
    else:
        if not _saveItems(fitTrackedData, pathArgs=pathArgs):
            return

    writeFitFile(fitTrackedData)
    popen('git add -f'.split()+[fitFile]).wait()

@gitDirOperation(repoDir)
def _saveItems(fitTrackedData, paths=None, pathArgs=None):
    trackedItems = getTrackedItems()
    if not paths:
        paths = getValidFitPaths(pathArgs, trackedItems.union(fitTrackedData))

    print 'Checking for changes...',
    changes = getChangedItems(fitTrackedData, trackedItems, paths)
    if sum(len(l) for l in changes) == 0:
        print 'No changes detected!'
        return
    else:
        print 'Done.'

    modified, added, removed, untracked = changes

    print 'Computing hashes for new items...',
    sizes = [s.st_size for s in [stat(f) for f in added]]
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    added = zip(added, zip(p.communicate('\n'.join(added))[0].strip().split('\n'), sizes))
    modified.update(added)
    print 'Done.'

    fitTrackedData.update(modified)
    for i in removed:
        del fitTrackedData[i]
    for i in untracked:
        del fitTrackedData[i]

    print 'Caching new and modified items...',
    for filePath,(objHash, size) in modified.iteritems():
        placeObject(objHash, filePath)
    print 'Done.'

    return True

