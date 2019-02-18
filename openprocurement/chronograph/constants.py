# -*- coding: utf-8 -*-
from datetime import timedelta, time

ROUNDING = timedelta(minutes=29)
MIN_PAUSE = timedelta(minutes=3)
BIDDER_TIME = timedelta(minutes=6)
SERVICE_TIME = timedelta(minutes=9)
STAND_STILL_TIME = timedelta(days=1)
SMOOTHING_MIN = 10
SMOOTHING_REMIN = 60
# value should be greater than SMOOTHING_MIN and SMOOTHING_REMIN
SMOOTHING_MAX = 300
