from pyramid.view import view_config

from openprocurement.chronograph.scheduler import (
    recheck_auction,
    resync_auctions,
    resync_auctions_back,
)


@view_config(route_name='home', renderer='json')
def home_view(request):
    return {'jobs': dict([
        (i.id, i.next_run_time.isoformat())
        for i in request.registry.scheduler.get_jobs()
    ])}


@view_config(route_name='resync_all', renderer='json')
def resync_all(request):
    return resync_auctions(request)


@view_config(route_name='resync_back', renderer='json')
def resync_back(request):
    return resync_auctions_back(request)


@view_config(route_name='recheck', renderer='json')
def recheck(request):
    return recheck_auction(request)
