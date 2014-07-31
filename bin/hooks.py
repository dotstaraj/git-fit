from fit import fitFile, writeFitFile, gitDirOperation, repoDir
from fit import readFitFile, readFitFileForRevision
from changes import getStagedOffenders, saveItems, restoreItems
from objects import findObject, placeObject
from merge import cleanupMergeArtifacts, getMergedFit
from subprocess import PIPE, Popen as popen
from textwrap import fill as wrapline
from os import stat

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


@gitDirOperation(repoDir)
def postCheckout(fitTrackedData, oldRev):
    mergeOld = readFitFileForRevision(oldRev)
    mergeNew = fitTrackedData
    mergeWorking = dict(mergeOld)
    saveItems(mergeWorking, quiet=True)
    mergeWorking, conflicts, modified, added, removed = getMergedFit(mergeOld, mergeWorking, mergeNew)
    restoreItems(mergeWorking, modified, added, removed, quiet=True)

@gitDirOperation(repoDir)
def postCommit(fitTrackedData):
    cleanupMergeArtifacts()
    # 1 notify warning if un-committed changes exist
    # 2 Notify warning to unignore items that were untracked in the commit
    # 3 cache new committed items
        '''
        print 'Caching new and modified items...',
        for filePath,(objHash, size) in modified.iteritems():
            placeObject(objHash, filePath)
        print 'Done.'
        '''

@gitDirOperation(repoDir)
def preCommit(fitTrackedData):
    _checkOffenders(fitTrackedData)
    _checkObjectsIntegrity(fitTrackedData)

def _checkOffenders(fitTrackedData):
    offenders = getStagedOffenders()

    if sum(len(l) for l in offenders) == 0:
        exit()

    conflict = [('F ', i) for i in offenders[0]]
    binary = [('B ', i) for i in offenders[1]]
    
    print '\n'.join([wrapline(l) for l in infoMsg[:4]])
    for c,f in sorted(conflict+binary, key=lambda i: i[1]):
        print '   ', c, f
    print '\n'.join([wrapline(l) for l in infoMsg[5:]])

    exit(1)

def _checkObjectsIntegrity(fitTrackedData):
    oldFit = readFitFileForRevision('HEAD')
    newFit = fitTrackedData
    workingFit = dict(oldFit)
    saveItems(workingFit, quiet=True)
    workingFit, conflicts, modified, added, removed = getMergedFit(oldFit, workingFit, newFit)
