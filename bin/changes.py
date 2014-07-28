from fit import fitStats, fitFile, gitDirOperation, repoDir
from fit import readStatFile, writeStatFile, refreshStats, writeFitFile
from objects import findObject, placeObject, getObjectInfo, getUpstreamItems, getDownstreamItems
from paths import getValidFitPaths
import merge
from subprocess import Popen as popen, PIPE
from os.path import exists, dirname, getsize
from os import remove, makedirs, stat
from shutil import copyfile
from itertools import chain
import re
from threading import Thread as thread
from sys import stdout

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

def printStatus(fitTrackedData, pathArgs=None, legend=True, showall=False):
    if legend:
        printLegend()

    if merge.isMergeInProgress():
        print merge.conflictMsg
        return

    modified, added, removed, untracked, unchanged = getChangedItems(fitTrackedData, pathArgs=pathArgs)
    conflict, binary = getStagedOffenders()
    unchanged = unchanged if showall else []

    toupload = set()
    todownload = set()

    paths = fitTrackedData if not pathArgs else getValidFitPaths(pathArgs, set(fitTrackedData), repoDir)
    toupload = getUpstreamItems(fitTrackedData, paths)
    todownload = getDownstreamItems(fitTrackedData, paths)

    offenders = set(chain(conflict, binary))

    modified =  [('*  ', i) for i in set(modified)-offenders]
    added =     [('+  ', i) for i in added-offenders]
    removed =   [('-  ', i) for i in removed]
    untracked = [('~  ', i) for i in untracked-offenders]
    conflict =  [('F  ', i) for i in conflict]
    binary =    [('B  ', i) for i in binary]
    unchanged = [('   ', i) for i in unchanged]

    if all(len(l) == 0 for l in [added,removed,untracked,modified,conflict,binary,toupload,todownload,unchanged]):
        print 'Nothing to show (no problems or changes detected).'
        return

    if any(len(l) > 0 for l in [added,removed,untracked,modified,conflict,binary,unchanged]):
        print
        for c,f in sorted(untracked+modified+added+removed+conflict+binary+unchanged, key=lambda i: i[1]):
            print '  ', c, f
        print

    if len(toupload) > 0:
        print ' * %s object(s) may need to be uploaded. Run \'git-fit put\' -s for details.'%len(toupload)
    if len(todownload) > 0:
        print ' * %d object(s) need to be downloaded. Run \'git-fit get\' -s for details.'%len(todownload)

def _gitHashInputProducer(stream, items):
    numItems = len(items)
    numDigits = str(len(str(numItems)+''))
    for i,j in enumerate(items):
        print ('\rComputing hashes for new objects...%6.2f%%  '+'%'+numDigits+'s/%'+numDigits+'s')%(i*100./numItems, i, numItems),
        print >>stream, j
        stdout.flush()
        stream.flush()
    print '\rComputing hashes for new objects...Done.'+' '*(9+int(numDigits)*2)
    stream.close()

def computeHashes(items):
    if not items:
        return []

    hashes = []
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    thread(target=_gitHashInputProducer, args=(p.stdin,items)).start()
    for l in p.stdout:
        hashes.append(l.strip())
    return hashes

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
    touchedHashes = dict(zip(touchedItems, computeHashes(touchedItems)))

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
        if i in touchedHashes and touchedHashes[i] != trackedHash:
            modifiedItems[i] = (touchedHashes[i], size)
        elif size > 0 and i in statsOld and statsOld[i][0] != trackedHash:
            modifiedItems[i] = (statsOld[i][0], size)

    # Update our cached stats if necessary
    writeStatCache = False
    if len(touchedHashes) > 0:
        writeStatCache = True
        for f in touchedHashes:
            statsOld[f] = (touchedHashes[f], statsNew[f])

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

@gitDirOperation(repoDir)
def getChangedItems(fitTrackedData, paths=None, pathArgs=None):

    # The tracked items according to the saved/committed .fit file
    expectedItems = set(fitTrackedData)

    # The tracked items in the working directory according to the
    # currently set fit attributes
    fitSetRgx = re.compile('(.*): fit: set')
    p = popen('git ls-files -o'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    trackedItems = {m.group(1) for m in [fitSetRgx.match(l) for l in p.stdout] if m}

    # Get valid, fit-friendly repo paths from given arbitrary path arguments
    if not paths and pathArgs:
        paths = getValidFitPaths(pathArgs, expectedItems | trackedItems, repoDir)
        if not paths:
            return ({}, set(), set(), set(), set())

    if paths:
        expectedItems &= paths
        trackedItems &= paths

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

    unchangedItems = existingItems - set(modifiedItems)

    return (modifiedItems, newItems, removedItems, untrackedItems, unchangedItems)

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
def checkForChanges(fitTrackedData, paths=None, pathArgs=None):
    changes = getChangedItems(fitTrackedData, paths=paths, pathArgs=pathArgs)
    if not any(changes):
        print 'No changes detected!'
        return
    
    return changes

@gitDirOperation(repoDir)
def restore(fitTrackedData, quiet=False, pathArgs=None):
    changes = checkForChanges(fitTrackedData, pathArgs=pathArgs)
    if not changes:
        return

    modified, added, removed, untracked, unchanged = changes

    for i in sorted(added):
        remove(i)
        if not quiet:
            print 'Removed: %s'%i

    missing = 0
    touched = {}

    result = _restoreItems('Added', sorted(removed), fitTrackedData, quiet=quiet)
    missing += result[0]
    touched.update(result[1])
    result = _restoreItems('Replaced', sorted(modified), fitTrackedData, quiet=quiet)
    missing += result[0]
    touched.update(result[1])

    print

    refreshStats(touched)

    if missing > 0:
        print 'For %d of the fit objects just restored, only empty stub files were'%missing
        print 'created in their stead. This is because those objects are not cached and must be'
        print 'downloaded. To start this download, run \'git-fit get\' with the same path arguments'
        print 'passed to \'git-fit restore\' restore (if any).\n'

def _restoreItems(restoreType, objects, fitTrackedData, quiet=False):
    missing = 0
    touched = {}
    for filePath in objects:
        objHash = fitTrackedData[filePath][0]
        objPath = findObject(objHash)
        fileDir = dirname(filePath)
        fileDir and (exists(fileDir) or makedirs(fileDir))
        if objPath:
            if not quiet:
                print '%s: %s'%(restoreType, filePath)
            copyfile(objPath, filePath)
            touched[filePath] = objHash
        else:
            if not quiet:
                print '%s (empty): %s'%(restoreType, filePath)
            open(filePath, 'w').close()  #write a 0-byte file as placeholder
            missing += 1

    return (missing, touched)

@gitDirOperation(repoDir)
def save(fitTrackedData, pathArgs=None):
    if merge.isMergeInProgress():
        if pathArgs:
            print 'A .fit merge is currently in progress and unresolved. Path arguments to'
            print '\'git-fit save\' cannot be given. If you have finished making selections'
            print ' in FIT_MERGE, run \'git-fit save\' without any arguments to complete'
            print 'conflict resolution.'
            return

        result = merge.resolve(fitTrackedData)
        if not result:
            return
        updateFitFile, paths = result
        _saveItems(fitTrackedData, paths=paths)
    else:
        if not (_saveItems(fitTrackedData, pathArgs=pathArgs) or updateFitFile):
            return

    writeFitFile(fitTrackedData)
    popen('git add -f'.split()+[fitFile]).wait()

@gitDirOperation(repoDir)
def _saveItems(fitTrackedData, paths=None, pathArgs=None):
    changes = checkForChanges(fitTrackedData, paths=paths, pathArgs=pathArgs)
    if not changes:
        return

    modified, added, removed, untracked, unchanged = changes

    sizes = [s.st_size for s in [stat(f) for f in added]]
    newHashes = computeHashes(list(added))
    added = zip(added, zip(newHashes, sizes))
    modified.update(added)

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

