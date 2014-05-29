from fit import getStagedOffenders, getChangedItems, fitFile
from fit import gitDirOperation, repoDir
from objects import findObject, placeObject
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
def postCheckout(fitTrackedData, oldRef, newRef, branch):
    if oldRef == newRef or branch != '1':
        return

@gitDirOperation(repoDir)
def postCommit(fitTrackedData):
    pass

@gitDirOperation(repoDir)
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



    print 'git-fit: Checking for changes...',
    changed = getChangedItems(fitTrackedData)
    print 'Done.'
    if sum(len(l) for l in changed) == 0:
        exit(0)

    modified, added, removed, untracked = changed

    print 'git-git: Computing hashes for new items...',
    sizes = [s.st_size for s in [stat(f) for f in added]]
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    added = zip(added, zip(p.communicate('\n'.join(added))[0].strip().split('\n'), sizes))
    print 'Done.'

    for i in removed:
        del fitTrackedData[i]
    for i in untracked:
        del fitTrackedData[i]

    fitTrackedData.update(modified)
    fitTrackedData.update(added)

    print 'git-fit: Caching new and modified items...',
    added.update(modified)
    for filePath,(objHash, size) in added:
        placeObject(objHash, filePath)
    print 'Done.'

    writeFitFile(fitTrackedData)
    popen('git add -f'.split()+[fitFile]).wait()
