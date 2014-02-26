from fit import getChangedItems, getStagedOffenders
from itertools import chain

'''
parser = argparse.ArgumentParser(prog='fit')

parser.add_argument('-l', '--legend', action='store_true', help='Show legend of status codes for changed items and their meaning')
parser.add_argument('-a', '--all', action='store_true', help='List all unchanged items in addition to the changed ones')
'''

def printStatus():
    added, removed, modified, untracked = getChangedItems()
    conflict, binary, large = getStagedOffenders()

    if all(len(l) == 0 for l in [added,removed,untracked,modified,conflict,binary,large]):
        print 'Nothing to show: no problems or changes detected.'
        return

    offenders = set(chain(conflict, binary, large))
    
    added =     [('+  ', i) for i in set(added)-offenders]
    removed =   [('-  ', i) for i in removed]
    untracked = [('~  ', i) for i in set(untracked)-offenders]
    modified =  [('*  ', i) for i in set(modified)-offenders]
    conflict =  [('!F ', i) for i in conflict]
    binary =    [('!B ', i) for i in binary]
    large =     [('!L ', i) for i in large]

    if len(offenders) > 0:
        print '\nThe changes with a \'!\' below are problems that will abort a git commit:'
    else:
        print '\nThe following changes will be automatically recorded in a git commit:'
    print '(run with --legend option to see what the status symbols mean)\n'

    for c,f in sorted(added+removed+untracked+modified+conflict+binary+large, key=lambda i: i[1]):
        print c, f
    print

