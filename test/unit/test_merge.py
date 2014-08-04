
import unittest

from fitlib import merge
from uuid import uuid4 as uid

def getDict(numItems = 1):
    return {u.hex: u.int for u in [uid() for i in range(numItems)]}

class TestFitDiff(unittest.TestCase):
    def setUp(self):
        self.longMessage = True

    def diff(self, old, new, expected):
        actual = merge.fitDiff(old, new)

        self.assertEqual(expected[0], actual[0], '\n\nerror: "modified" not as expected')
        self.assertEqual(expected[1], actual[1], '\n\nerror: "added" not as expected')
        self.assertEqual(expected[2], actual[2], '\n\nerror: "removed" not as expected')

    def testAllEmpty(self):
        old, new = {}, {}
        expected = set(), set(), set()
        self.diff(old, new, expected)

    def testOldEmpty(self):
        old, new = {}, getDict()
        expected = set(), set(new), set()
        self.diff(old, new, expected)

    def testNewEmpty(self):
        old, new = getDict(), {}
        expected = set(), set(), set(old)
        self.diff(old, new, expected)

    def testExaclySame(self):
        old = getDict(5)
        new = dict(old)
        expected = set(), set(), set()
        self.diff(old, new, expected)

    def testSomeAdded(self):
        old = getDict(2)
        new = getDict(2)
        new.update(old)
        expected = set(), set(new)-set(old), set()
        self.diff(old, new, expected)

    def testSomeRemoved(self):
        old = getDict(2)
        new = getDict(2)
        old.update(new)
        expected = set(), set(), set(old)-set(new)
        self.diff(old, new, expected)

    def testSomeModified(self):
        old = getDict(4)
        new = dict(old)

        modified = old.keys()[:2]
        for k in modified:
            new[k] = uid().int

        expected = set(modified), set(), set()
        self.diff(old, new, expected)

    def testMixedChanges(self):
        modified = {'a':1, 'b':2}
        added = {'c':3, 'd':4}
        removed = {'e':5, 'f':6}

        old = dict(removed)
        new = dict(added)
        old.update(modified)
        new.update({u:i+1 for u,i in modified.iteritems()})

        expected = set(modified), set(added), set(removed)
        self.diff(old, new, expected)


