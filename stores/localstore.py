from os.path import exists, join as joinpath, dirname
from shutil import copy, rmtree
from tempfile import mkdtemp
import objects
from subprocess import Popen as popen
from fit import fitDir

class Store(objects.Store):

    def __init__(self, *args, **kwds):
        self.dir = joinpath(fitDir, 'store')

    def get(self, key, dst, size):
        if exists(key):
            copy(key, dst)
            return True

    def put(self, src, dst, size):
        if exists(src):
            dst = joinpath(self.dir, dst)
            popen(['mkdir', '-p', dirname(dst)]).wait()
            popen(['cp', src, dst]).wait()
            return True

    def check(self, key):
        path = joinpath(self.dir, key)
        return path if exists(path) else None
