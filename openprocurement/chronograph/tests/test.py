# -*- coding: utf-8 -*-
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from logging import getLogger

from time import sleep

import requests

from openprocurement.chronograph import TZ
from openprocurement.chronograph.tests.utils import update_json
from openprocurement.chronograph.tests.base import BaseWebTest, BaseAuctionWebTest
from openprocurement.chronograph.tests.data import test_bids, test_lots, test_auction_data

LOGGER = getLogger(__name__)
test_auction_data_quick = deepcopy(test_auction_data)
test_auction_data_quick.update({
    "enquiryPeriod": {
        'startDate': datetime.now(TZ).isoformat(),
        "endDate": datetime.now(TZ).isoformat()
    },
    'tenderPeriod': {
        'startDate': datetime.now(TZ).isoformat(),
        "endDate": datetime.now(TZ).isoformat()
    }
})
test_auction_data_test_quick = deepcopy(test_auction_data_quick)
test_auction_data_test_quick['mode'] = 'test'


class SimpleTest(BaseWebTest):

    def test_list_jobs(self):
        response = self.app.get('/')
        self.assertEqual(response.status, '200 OK')
        self.assertIn('jobs', response.json)
        self.assertEqual(len(response.json['jobs']), 1)

    def test_resync_all(self):
        response = self.app.get('/resync_all')
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)

    def test_resync_back(self):
        response = self.app.get('/resync_back')
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)

    def test_recheck_one(self):
        response = self.app.get('/recheck/all')
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)


class AuctionsTest(BaseAuctionWebTest):

    def test_list_jobs(self):
        response = self.app.get('/')
        self.assertEqual(response.status, '200 OK')
        self.assertIn('jobs', response.json)
        self.assertEqual(len(response.json['jobs']), 1)
        self.assertIn('resync_all', response.json['jobs'])
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = self.app.get('/')
        self.assertEqual(response.status, '200 OK')
        self.assertIn('jobs', response.json)
        self.assertEqual(len(response.json['jobs']), 2)
        self.assertIn("recheck_{}".format(self.auction_id), response.json['jobs'])


class AuctionTest(BaseAuctionWebTest):
    scheduler = False

    def test_wait_for_enquiryPeriod(self):
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.enquiries')

    def test_switch_to_auctioning_enquiryPeriod(self):
        response = requests.patch('{}/{}'.format(self.app.app.registry.full_url, self.auction_id), {
            'data': {
                "enquiryPeriod": {
                    "endDate": datetime.now(TZ).isoformat()
                },
                'tenderPeriod': {
                    'startDate': None
                }
            }
        })
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.tendering')

    def test_switch_to_auctioning_tenderPeriod(self):
        response = requests.patch('{}/{}'.format(self.app.app.registry.full_url, self.auction_id), {
            'data': {
                "enquiryPeriod": {
                    "endDate": datetime.now(TZ).isoformat()
                },
                'tenderPeriod': {
                    'startDate': datetime.now(TZ).isoformat()
                }
            }
        })
        for _ in range(100):
            response = self.app.get('/recheck/' + self.auction_id)
            self.assertEqual(response.status, '200 OK')
            self.assertNotEqual(response.json, None)
            response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
            response.json = response.json()
            auction = response.json['data']
            if response.json['data']['status'] == 'active.tendering':
                break
            sleep(0.1)
        self.assertEqual(auction['status'], 'active.tendering')

    def test_wait_for_tenderPeriod(self):
        response = requests.patch('{}/{}'.format(self.app.app.registry.full_url, self.auction_id), {
            'data': {
                "enquiryPeriod": {
                    "endDate": datetime.now(TZ).isoformat()
                },
                'tenderPeriod': {
                    'startDate': (datetime.now(TZ) + timedelta(hours=1)).isoformat()
                }
            }
        })
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.enquiries')

    def test_switch_to_unsuccessful(self):
        response = requests.patch('{}/{}'.format(self.app.app.registry.full_url, self.auction_id), {
            'data': {
                "enquiryPeriod": {
                    "endDate": datetime.now(TZ).isoformat()
                },
                'tenderPeriod': {
                    'startDate': datetime.now(TZ).isoformat(),
                    "endDate": datetime.now(TZ).isoformat()
                }
            }
        })
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.tendering')
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'unsuccessful')


class AuctionLotTest(AuctionTest):
    initial_lots = test_lots


class AuctionTest2(BaseAuctionWebTest):
    scheduler = False
    quick = True
    initial_bids = test_bids[:1]

    def test_switch_to_qualification(self):
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.qualification')

    def test_switch_to_unsuccessful(self):
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.qualification')
        self.assertIn('awards', auction)
        award = auction['awards'][0]
        response = requests.patch('{}/{}'.format(self.app.app.registry.full_url, self.auction_id) + '/awards/' + award['id'], {"data": {"status": "unsuccessful"}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-type'], 'application/json')
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertNotEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.awarded')

        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        auction = response.json()['data']
        auction['awards'][0]['complaintPeriod']['endDate'] = datetime.now(TZ).isoformat()
        update_json(self.api, 'auction', self.auction_id, {"data": auction})
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'unsuccessful')


class AuctionLotTest2(AuctionTest2):
    initial_lots = test_lots


class AuctionTest3(BaseAuctionWebTest):
    scheduler = False
    quick = True
    initial_bids = test_bids

    def test_switch_to_auction(self):
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        response.json = response.json()
        auction = response.json['data']
        self.assertEqual(auction['status'], 'active.auction')

    def test_reschedule_auction(self):
        response = self.app.get('/recheck/' + self.auction_id)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json, None)
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        auction = response.json()['data']
        self.assertEqual(auction['status'], 'active.auction')
        if self.initial_lots:
            self.assertNotIn('auctionPeriod', auction)
            self.assertIn('auctionPeriod', auction['lots'][0])
            self.assertIn('shouldStartAfter', auction['lots'][0]['auctionPeriod'])
            self.assertNotIn('startDate', auction['lots'][0]['auctionPeriod'])
            self.assertGreater(auction['lots'][0]['auctionPeriod']['shouldStartAfter'], auction['lots'][0]['auctionPeriod'].get('startDate'))
        else:
            self.assertIn('auctionPeriod', auction)
            self.assertIn('shouldStartAfter', auction['auctionPeriod'])
            self.assertNotIn('startDate', auction['auctionPeriod'])
            self.assertGreater(auction['auctionPeriod']['shouldStartAfter'], auction['auctionPeriod'].get('startDate'))
        response = requests.get('{}/{}'.format(self.app.app.registry.full_url, self.auction_id))
        auction = response.json()['data']
        self.assertEqual(auction['status'], 'active.auction')


class AuctionLotTest3(AuctionTest3):
    initial_lots = test_lots


class AuctionTest4(AuctionTest3):
    sandbox = True


class AuctionLotTest4(AuctionTest4):
    initial_lots = test_lots


def suite():
    tests = unittest.TestSuite()
    tests.addTest(unittest.makeSuite(AuctionLotTest))
    tests.addTest(unittest.makeSuite(AuctionLotTest2))
    tests.addTest(unittest.makeSuite(AuctionLotTest3))
    tests.addTest(unittest.makeSuite(AuctionLotTest4))
    tests.addTest(unittest.makeSuite(AuctionTest))
    tests.addTest(unittest.makeSuite(AuctionTest2))
    tests.addTest(unittest.makeSuite(AuctionTest3))
    tests.addTest(unittest.makeSuite(AuctionTest4))
    tests.addTest(unittest.makeSuite(AuctionsTest))
    tests.addTest(unittest.makeSuite(SimpleTest))
    return tests


if __name__ == '__main__':
    unittest.main(defaultTest='suite', exit=False)
