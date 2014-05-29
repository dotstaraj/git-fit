from fit import gitDirOperation, repoDir, readFitFile, writeFitFile
from fit import mineFitFile, otherFitFile, conflictFile
from os import path
from shutil import move

conflictMsg = '''
********** git-fit found conflicts during the merge **********
Either a merge, rebase, or other command requiring a merge caused
conflicts in fit managed items. Fit has already handled non-
conflicting changes, but the conflicts need to be manually
resolved. SEE THE "FIT_MERGE" FILE in your project root directory
for instructions on resolving the conflicts. Do not continue with
the merge until these conflicts have been resolved!
********** git-fit found conflicts during the merge **********
'''

conflictIntructions = '''\
# HOW TO RESOLVE THESE CONFLICTS:
# For each conflicted item, there is a row below consisting of three columns:
#
#   <"OUR"-CHANGE> | <"THEIR"-CHANGE> |  <ITEM_PATH>
#
# Example rows:
#
#   * | - |  someDirectory/file1
#   + | + |  directory2/file2
#
# (symbol meanings: "+" = "added", "-" = "removed", "*" = "modified")
#
# Each conflict MUST be resolved by selecting the version of the item that
# should be kept: "OUR" or "THEIR" (individual items cannot be manually
# edited for resolution). For each row, make this selection by DELETING the
# "OUR/THEIR"-CHANGE character for the version you want to DISCARD. The version
# that is not deleted is the version that fit will apply. However, deleting an
# entire row is equivalent to deleting "THEIR" (and thus # keeping "OUR") for
# that item. Also, deleting the entire file is equivalent to choosing to
# resolve ALL conflicts with "OUR".
#
# (1) Once a selection for EACH row has been made as described, save this file.
# (2) Run "git fit --save", which will check for this conflict resolutions file
#     and update the .fit file with the selected resolutions.
# (3) Then simply "git add .fit" and continue with the merge/rebase/amend as
#     normal (the .fit file is located in root project directory). If for any
#     row(s) a selection has not been made or containes error, the attempted
#     commit will be aborted.
#
# REMEMBER:
# If these conflicts resulted from a git REBASE operation, then
# "ours" and "theirs" refer to the OPPOSITE versions than what intuitively
# makes sense from your point of view. In other words, for rebase, "ours"
# refers to the version that you are bringing IN to your current branch. And
# likewise, "theirs" refers to the version in YOUR current branch itself.

'''.split('\n')


def mergeDriver(common, mine, other):
    merged = getMergedFit(readFitFile(common), readFitFile(mine), readFitFile(other))
    writeFitFile(merged['fit'], mine)

    if merged['conflicts']:
        writeConflictFile(merged['conflicts'])
        move(mine, mineFitFile)
        move(other, otherFitFile)
        print conflictMsg
        exit(1)

    exit(0)

def fitDiff(old, new):
    oldItems = set(old)
    newItems = set(new)

    added = newItems - oldItems
    removed = oldItems - newItems
    modified = {i for i in (oldItems & newItems) if old[i][0] != new[i][0]}

    return added,removed,modified

@gitDirOperation(repoDir)
def writeConflictFile(conflicts):
    lines =  [('+ | +', c) for c in conflicts['add']]
    lines += [('* | *', c) for c in conflicts['mod']]
    lines += [('* | -', c) for c in conflicts['modRem']]
    lines += [('- | *', c) for c in conflicts['remMod']]

    lines.sort(key=lambda a: a[1])

    fileout = open(conflictFile, 'w')
    fileout.write('\n'.join(conflictIntructions))
    fileout.write('\n'.join(["  %s |  %s"%l for l in lines]))
    fileout.close()

def isConflictLineError(l):
    return len(l) != 3 or len(l[0]) > 1 or len(l[1]) > 1 or len(l[0]) == 0 and len(l[1]) == 0

@gitDirOperation(repoDir)
def getConflictResolutions():
    if not path.exists(conflictFile):
        return None

    lines = [(i+1, l.strip()) for i,l in enumerate(open(conflictFile).readlines()) if not l.startswith('#')]
    lines = {(i,tuple(c.strip() for c in l.split('|'))) for i,l in lines if l != ''}


    errors = {(i,l) for i,l in lines if isConflictLineError(l)}
    lines -= errors
    unresolved = {(i,l) for i,l in lines if len(l[0]) != 0 and len(l[1]) != 0}
    lines -= unresolved

    mine = readFitFile(mineFitFile)
    other = readFitFile(otherFitFile)

    added = []
    removed = []
    for tmp,(tmp, change, item) in lines:
        if change == '':
            continue
        if change == '-':
            removed.append(item)
        else:
            added.append((item, other[item]))

    return {'errors': errors or None, 'unresolved': unresolved or None, 'removed': removed, 'added': added}

def getMergedFit(common, mine, other):
    mineAdd,mineRem,mineMod = fitDiff(common, mine)
    otherAdd,otherRem,otherMod = fitDiff(common, other)

    addCon = {i for i in (mineAdd & otherAdd) if mine[i][0] != other[i][0]}
    modCon = {i for i in (mineMod & otherMod) if mine[i][0] != other[i][0]}
    modRemCon = mineMod & otherRem
    remModCon = otherMod & mineRem

    allCon = addCon | modCon | modRemCon | remModCon
    
    for i in (otherAdd | otherMod) - allCon:
        mine[i] = other[i]
    for i in (otherRem - mineRem) - allCon:
        del mine[i]

    result = {'conflicts': None, 'fit': mine}
    
    if len(allCon) > 0:
        result['conflicts'] = {
            'add': addCon,
            'mod': modCon,
            'modRem': modRemCon,
            'remMod': remModCon
        }

    return result
