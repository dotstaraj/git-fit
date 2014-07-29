from tempfile import mkdtemp
from os import chdir, getcwd, devnull as DEVNULL
from os.path import isdir
from subprocess import call as pcall
from shutil import rmtree
from uuid import uuid4 as uid

from sys import path
from os.path import dirname, realpath, join
path.append(join(dirname(realpath(__file__)), '..', 'bin'))
from fit import gitDirOperation

def shell(cmd):
    return pcall('set -e\n' + cmd, shell=True)

class GitFitRepo:
    def __init__(self, gitDir=None):
        self.gitDir = gitDir if gitDir != None else mkdtemp()
        self.numRevisions = 0
        self.attributes = {}

        cwd = getcwd()
        chdir(self.gitDir)
        shell('git init')
        chdir(cwd)

    @gitDirOperation
    def fitInit(self):
        shell('git-fit')

    @gitDirOperation
    def add(self, path=None, binary=False, stage=True):
        if path == None:
            path = str(uid())

        if binary:
            content = r'\0binary file'
        else:
            content = 'text file'

        opts = {'path': path, 'content': content}

        cmd = '''
            mkdir -p `dirname "%(path)s"`
            printf '%(content)s\n' > "%(path)s"
        '''

        if stage:
            cmd += '''
                git add -v "%(path)s"
            '''

        shell(cmd % opts)

        return path

    @gitDirOperation
    def remove(self, path, stage=True):
        opts = {'path': path}

        cmd = 'rm -rf %(path)s'

        if stage:
            cmd = '''
                git add -uAv %(path)s
            '''

        return shell(cmd % opts) == 0

    @gitDirOperation
    def setFitAttr(self, path, fit=False):
        opts = {'path': path, 'fit': '' if fit else '-', 'dirpattern': '/**' if isdir(path) else ''}
        shell('printf "%(path)s%(dirpattern)s %(fit)sfit\n" >> .gitattributes'%opts)

    @gitDirOperation
    def commit(self):
        shell('git commit -m "revision %d"'%self.numRevisions)
        self.numRevisions += 1

    @gitDirOperation
    def checkout(self, revisionFromHead):
        if revisionFromHead >= self.numRevisions:
            revisionFromHead = self.numRevisions - 1

        shell('git checkout master' + '^'*revisionFromHead)

    def destroy(self):
        rmtree(self.gitDir)

