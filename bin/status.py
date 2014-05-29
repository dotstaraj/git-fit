from fit import getChangedItems, getStagedOffenders
from objects import getUnsyncedObjects
from itertools import chain

'''
parser = argparse.ArgumentParser(prog='fit')

parser.add_argument('-l', '--legend', action='store_true', help='Show legend of status codes for changed items and their meaning')
parser.add_argument('-a', '--all', action='store_true', help='List all unchanged items in addition to the changed ones')
'''

def printLegend():
    print 'Meaning of status symbols:'
    print '-------------------------------------------------------------------------------'
    print '^   locally cached fit object that MAY need to be uploaded to fulfill a commit'
    print '    (run "git fit --put -s" to check and refresh, or without -s to upload if needed)'
    print
    print '*   modified'
    print '+   new/added (fit will start tracking upon commit)'
    print '-   removed (physically deleted, fit will discontinue tracking it upon commit)'
    print '~   untracked (marked by you to be ignored by fit, fit will discontinue tracking it upon commit)'
    print
    print '!   an item staged for commit in git that will cause fit to abort the commit'
    print '!F  an item fit is already tracking, but is also currently staged for commit in git'
    print '!B  a binary file staged for commit in git that fit has not been told to ignore'
    print '-------------------------------------------------------------------------------'
    print

def printStatus(fitTrackedData, paths, legend=True):
    if legend:
        printLegend()

    unsynced = getUnsyncedObjects()
    unsynced = [p for p in paths if fitTrackedData[p][0] in unsynced]

    modified, added, removed, untracked = getChangedItems(fitTrackedData)
    conflict, binary = getStagedOffenders()

    offenders = set(chain(conflict, binary))
    
    paths = set(paths)

    # TODO: filter by paths also for added, conflict, and binary!!
    unsynced =  [('^  ', i) for i in unsynced]
    modified =  [('*  ', i) for i in set(modified)-offenders if i in paths]
    added =     [('+  ', i) for i in set(added)-offenders]
    removed =   [('-  ', i) for i in removed if i in paths]
    untracked = [('~  ', i) for i in set(untracked)-offenders if i in paths]
    conflict =  [('!F ', i) for i in conflict]
    binary =    [('!B ', i) for i in binary]

    if all(len(l) == 0 for l in [added,removed,untracked,modified,conflict,binary,unsynced]):
        print 'Nothing to show (no problems or changes detected).'
        return

    print
    for c,f in sorted(untracked+modified+added+removed+conflict+binary+unsynced, key=lambda i: i[1]):
        print '  ', c, f
    print
