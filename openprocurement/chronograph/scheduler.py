# -*- coding: utf-8 -*-
import requests
from datetime import timedelta
from json import dumps
from logging import getLogger
from openprocurement.chronograph.utils import (
    context_unpack, update_next_check_job, push,
    get_request,
    get_now
)
from os import environ
from pytz import timezone
from time import sleep

from urllib import urlencode
from collections import OrderedDict

LOGGER = getLogger(__name__)
TZ = timezone(environ['TZ'] if 'TZ' in environ else 'Europe/Kiev')

ADAPTER = requests.adapters.HTTPAdapter(pool_connections=3, pool_maxsize=3)
SESSION = requests.Session()
SESSION.mount('http://', ADAPTER)
SESSION.mount('https://', ADAPTER)

BASIC_OPT_FIELDS = ['status', 'next_check']
PLANNING_OPT_FIELDS = ['status', 'next_check', 'auctionPeriod', 'procurementMethodType', 'lots', 'auctionParameters']


def recheck_auction(request):
    auction_id = request.matchdict['auction_id']
    scheduler = request.registry.scheduler
    url = '{}/{}'.format(request.registry.full_url, auction_id)
    api_token = request.registry.api_token
    recheck_url = request.registry.callback_url + 'recheck/' + auction_id
    request_id = request.environ.get('REQUEST_ID', '')
    next_check = None
    r = SESSION.patch(url,
                      data=dumps({'data': {'id': auction_id}}),
                      headers={'Content-Type': 'application/json', 'X-Client-Request-ID': request_id},
                      auth=(api_token, ''))
    if r.status_code != requests.codes.ok:
        LOGGER.error("Error {} on checking auction '{}': {}".format(r.status_code, url, r.text),
                     extra=context_unpack(request, {'MESSAGE_ID': 'error_check_auction'}, {'ERROR_STATUS': r.status_code}))
        if r.status_code not in [requests.codes.forbidden, requests.codes.not_found]:
            next_check = (get_now() + timedelta(minutes=1)).isoformat()
    elif r.json():
        next_check = r.json()['data'].get('next_check')
    if next_check:
        next_check = update_next_check_job(next_check, scheduler, auction_id, get_now(), recheck_url)
    return next_check and next_check.isoformat()


def process_listing(auctions, scheduler, callback_url):
    run_date = get_now()
    for auction in auctions:
        tid = auction['id']
        next_check = auction.get('next_check')
        if next_check:
            recheck_url = ''.join([callback_url, 'recheck/', tid])
            update_next_check_job(next_check, scheduler, tid, run_date, recheck_url, True)


def resync_auctions(request):
    next_url = request.params.get('url', '')
    opt_fields = ",".join(BASIC_OPT_FIELDS) if not request.registry.planning else ",".join(PLANNING_OPT_FIELDS)
    if not next_url or urlencode({"opt_fields": opt_fields}) not in next_url:
        query = urlencode(OrderedDict(mode='_all_', feed='changes', descending=1, opt_fields=opt_fields))
        next_url = '{}?{}'.format(request.registry.full_url, query)
    scheduler = request.registry.scheduler
    api_token = request.registry.api_token
    callback_url = request.registry.callback_url
    request_id = request.environ.get('REQUEST_ID', '')
    while True:
        try:
            r = get_request(next_url, auth=(api_token, ''), session=SESSION, headers={'X-Client-Request-ID': request_id})
            if r.status_code == requests.codes.not_found:
                next_url = ''
                break
            elif r.status_code != requests.codes.ok:
                break
            else:
                json = r.json()
                next_url = json['next_page']['uri']
                if "descending=1" in next_url:
                    run_date = get_now()
                    scheduler.add_job(push, 'date', run_date=run_date, timezone=TZ,
                                      id='resync_back', name="Resync back", misfire_grace_time=60 * 60,
                                      args=[callback_url + 'resync_back', {'url': next_url}],
                                      replace_existing=True)
                    next_url = json['prev_page']['uri']
            if not json['data']:
                break
            process_listing(json['data'], scheduler, callback_url)
            sleep(0.1)
        except Exception as e:
            LOGGER.error("Error on resync all: {}".format(repr(e)), extra=context_unpack(request, {'MESSAGE_ID': 'error_resync_all'}))
            break
    run_date = get_now() + timedelta(minutes=1)
    scheduler.add_job(push, 'date', run_date=run_date, timezone=TZ,
                      id='resync_all', name="Resync all",
                      misfire_grace_time=60 * 60,
                      args=[callback_url + 'resync_all', {'url': next_url}],
                      replace_existing=True)
    return next_url


def resync_auctions_back(request):
    next_url = request.params.get('url', '')
    opt_fields = ",".join(BASIC_OPT_FIELDS) if not request.registry.planning else ",".join(PLANNING_OPT_FIELDS)
    if not next_url:
        query = urlencode(OrderedDict(mode='_all_', feed='changes', descending=1, opt_fields=opt_fields))
        next_url = '{}?{}'.format(request.registry.full_url, query)
    scheduler = request.registry.scheduler
    api_token = request.registry.api_token
    callback_url = request.registry.callback_url
    request_id = request.environ.get('REQUEST_ID', '')
    LOGGER.info("Resync back started", extra=context_unpack(request, {'MESSAGE_ID': 'resync_back_started'}))
    while True:
        try:
            r = get_request(next_url, auth=(api_token, ''), session=SESSION, headers={'X-Client-Request-ID': request_id})
            if r.status_code == requests.codes.not_found:
                next_url = ''
                break
            elif r.status_code != requests.codes.ok:
                break
            json = r.json()
            next_url = json['next_page']['uri']
            if not json['data']:
                LOGGER.info("Resync back stopped", extra=context_unpack(request, {'MESSAGE_ID': 'resync_back_stoped'}))
                return next_url
            process_listing(json['data'], scheduler, callback_url)
            sleep(0.1)
        except Exception as e:
            LOGGER.error("Error on resync back: {}".format(repr(e)), extra=context_unpack(request, {'MESSAGE_ID': 'error_resync_back'}))
            break
    LOGGER.info("Resync back break", extra=context_unpack(request, {'MESSAGE_ID': 'resync_back_break'}))
    run_date = get_now() + timedelta(minutes=1)
    scheduler.add_job(push, 'date', run_date=run_date, timezone=TZ,
                      id='resync_back', name="Resync back", misfire_grace_time=60 * 60,
                      args=[callback_url + 'resync_back', {'url': next_url}],
                      replace_existing=True)
    return next_url
