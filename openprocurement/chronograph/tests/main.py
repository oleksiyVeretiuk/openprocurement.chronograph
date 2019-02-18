# -*- coding: utf-8 -*-

import unittest

from openprocurement.chronograph.tests import test


def suite():
    tests = unittest.TestSuite()
    tests.addTest(test.suite())
    return tests


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
