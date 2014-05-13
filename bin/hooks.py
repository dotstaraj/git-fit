from fit import getStagedOffenders, getChangedItems, gitDirOperation
from fit import fitFile, fitFileCopy, writeFitFile, readFitFile, repoDir
from objects import findObject, placeObject
from subprocess import PIPE, Popen as popen
from textwrap import fill as wrapline
from os import makedirs, stat, path, remove
from shutil import copyfile

@gitDirOperation(repoDir)
def postCheckout(fitTrackedData):
    lastFitTrackedData = readFitFile(fileToRead=fitFileCopy)
    p = popen(('git ls-files -o').split(), stdout=PIPE)
    nonGitItems = p.communicate()[0].strip().split('\n')
    itemsToRemove = (set(lastFitTrackedData) - set(fitTrackedData)) & set(nonGitItems)
    for i in itemsToRemove:
        remove(i)
    
    missing = 0
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        objPath = findObject(objHash)
        fileDir = path.dirname(filePath)
        fileDir and (path.exists(fileDir) or makedirs(fileDir))
        if objPath:
            copyfile(objPath, filePath)
        else:
            open(filePath, 'w').close()  #write a 0-byte file as placeholder
            missing += 1
    if missing > 0:
        print '* git-fit: %d fit objects are not cached and must be downloaded for the HEAD commit.'%missing
        print '* To download them, run "git fit --get". Optionally, provide paths to this command'
        print '* to selectively download only the objects you want.\n'

    writeFitFile(fitTrackedData)

def postCommit(fitTrackedData):
    print 'Caching objects for committed fit items...',
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        placeObject(objHash, filePath) if not findObject(objHash) else None
    print 'Done.'

# This msg string should be left exactly as it is in the multi-line string
infoMsg='''
********** git-fit has aborted this commit **********
The commit was aborted because the following items are staged in git:

<files-will-be-output-here>

F = explicitly included for git-fit through "fit" attribute
B = auto-detected binary file

This repository is configured to use git-fit. Any binary files that fit \
has not been told about will abort the commit.
********** git-fit has aborted this commit **********
'''.split('\n')

def preCommit(fitTrackedData):
    offenders = getStagedOffenders()
    if any(len(l) > 0 for l in offenders):
        conflict = [('F ', i) for i in offenders[0]]
        binary = [('B ', i) for i in offenders[1]]
        
        print '\n'.join([wrapline(l) for l in infoMsg[:4]])
        for c,f in sorted(conflict+binary, key=lambda i: i[1]):
            print '   ', c, f
        print '\n'.join([wrapline(l) for l in infoMsg[5:]])

        exit(1)

    modified, added, removed, untracked = getChangedItems(fitTrackedData)

    sizes = [s.st_size for s in [stat(f) for f in added]]
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    added = zip(added, zip(p.communicate('\n'.join(added))[0].strip().split('\n'), sizes))

    for i in removed:
        del fitTrackedData[i]
    for i in untracked:
        del fitTrackedData[i]
    fitTrackedData.update(modified)
    fitTrackedData.update(added)

    writeFitFile(fitTrackedData)
    popen('git add -f'.split()+[fitFile]).wait()

