from fit import fitFile, writeFitFile, gitDirOperation, repoDir
from changes import getStagedOffenders
from objects import findObject, placeObject
from merge import cleanupMergeArtifacts
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
def postCheckout(fitTrackedData):
    pass

@gitDirOperation(repoDir)
def postCommit(fitTrackedData):
    cleanupMergeArtifacts()
    # 1 notify warning if they have changes not committed
    # 2 cache items commmited

@gitDirOperation(repoDir)
def preCommit(fitTrackedData):
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
