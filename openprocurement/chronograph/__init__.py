import gevent.monkey
gevent.monkey.patch_all()
import os
from logging import getLogger
from apscheduler.schedulers.gevent import GeventScheduler as Scheduler
from couchdb import Server, Session
from couchdb.http import Unauthorized, extract_credentials
from datetime import datetime, timedelta
from openprocurement.chronograph.scheduler import push
from openprocurement.chronograph.utils import add_logging_context, get_full_url
from pyramid.config import Configurator
from pytz import timezone
from pyramid.events import ApplicationCreated, ContextFound
from pbkdf2 import PBKDF2

LOGGER = getLogger(__name__)

TZ = timezone(os.environ['TZ'] if 'TZ' in os.environ else 'Europe/Kiev')
SECURITY = {u'admins': {u'names': [], u'roles': ['_admin']}, u'members': {u'names': [], u'roles': ['_admin']}}
VALIDATE_DOC_ID = '_design/_auth'
VALIDATE_DOC_UPDATE = """function(newDoc, oldDoc, userCtx){
    if(newDoc._deleted) {
        throw({forbidden: 'Not authorized to delete this document'});
    }
    if(userCtx.roles.indexOf('_admin') !== -1 && newDoc.indexOf('_design/') === 0) {
        return;
    }
    if(userCtx.name === '%s') {
        return;
    } else {
        throw({forbidden: 'Only authorized user may edit the database'});
    }
}"""


def start_scheduler(event):
    app = event.app
    app.registry.scheduler.start()


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.add_subscriber(add_logging_context, ContextFound)
    config.include('pyramid_exclog')
    config.add_route('home', '/')
    config.add_route('resync_all', '/resync_all')
    config.add_route('resync_back', '/resync_back')
    config.add_route('resync', '/resync/{auction_id}')
    config.add_route('recheck', '/recheck/{auction_id}')
    config.add_route('calendar', '/calendar')
    config.add_route('calendar_entry', '/calendar/{date}')
    config.add_route('streams', '/streams')
    config.scan(ignore='openprocurement.chronograph.tests')
    config.add_subscriber(start_scheduler, ApplicationCreated)
    config.registry.api_token = os.environ.get('API_TOKEN', settings.get('api.token'))

    db_name = os.environ.get('DB_NAME', settings['couchdb.db_name'])
    server = Server(settings.get('couchdb.url'), session=Session(retry_delays=range(60)))
    if 'couchdb.admin_url' not in settings and server.resource.credentials:
        try:
            server.version()
        except Unauthorized:
            server = Server(extract_credentials(settings.get('couchdb.url'))[0], session=Session(retry_delays=range(60)))
    config.registry.couchdb_server = server
    if 'couchdb.admin_url' in settings and server.resource.credentials:
        aserver = Server(settings.get('couchdb.admin_url'), session=Session(retry_delays=range(10)))
        users_db = aserver['_users']
        if SECURITY != users_db.security:
            LOGGER.info("Updating users db security", extra={'MESSAGE_ID': 'update_users_security'})
            users_db.security = SECURITY
        username, password = server.resource.credentials
        user_doc = users_db.get('org.couchdb.user:{}'.format(username), {'_id': 'org.couchdb.user:{}'.format(username)})
        if not user_doc.get('derived_key', '') or PBKDF2(password, user_doc.get('salt', ''), user_doc.get('iterations', 10)).hexread(int(len(user_doc.get('derived_key', '')) / 2)) != user_doc.get('derived_key', ''):
            user_doc.update({
                "name": username,
                "roles": [],
                "type": "user",
                "password": password
            })
            LOGGER.info("Updating chronograph db main user", extra={'MESSAGE_ID': 'update_chronograph_main_user'})
            users_db.save(user_doc)
        security_users = [username, ]
        if db_name not in aserver:
            aserver.create(db_name)
        db = aserver[db_name]
        SECURITY[u'members'][u'names'] = security_users
        if SECURITY != db.security:
            LOGGER.info("Updating chronograph db security", extra={'MESSAGE_ID': 'update_chronograph_security'})
            db.security = SECURITY
        auth_doc = db.get(VALIDATE_DOC_ID, {'_id': VALIDATE_DOC_ID})
        if auth_doc.get('validate_doc_update') != VALIDATE_DOC_UPDATE % username:
            auth_doc['validate_doc_update'] = VALIDATE_DOC_UPDATE % username
            LOGGER.info("Updating chronograph db validate doc", extra={'MESSAGE_ID': 'update_chronograph_validate_doc'})
            db.save(auth_doc)
        # sync couchdb views
        db = server[db_name]
    else:
        if db_name not in server:
            server.create(db_name)
        db = server[db_name]
        # sync couchdb views
    config.registry.db = db

    jobstores = {
        #'default': CouchDBJobStore(database=db_name, client=server)
    }
    #executors = {
        #'default': ThreadPoolExecutor(5),
        #'processpool': ProcessPoolExecutor(5)
    #}
    job_defaults = {
        'coalesce': False,
        'max_instances': 3
    }
    config.registry.api_url = settings.get('api.url')
    config.registry.api_resource = settings.get('api.resource', 'auctions')
    config.registry.full_url = get_full_url(config.registry)
    config.registry.callback_url = settings.get('callback.url')
    scheduler = Scheduler(jobstores=jobstores,
                          #executors=executors,
                          job_defaults=job_defaults,
                          timezone=TZ)
    if 'jobstore_db' in settings:
        scheduler.add_jobstore('sqlalchemy', url=settings['jobstore_db'])
    config.registry.planning = bool(int(settings.get('planning', '1')))
    config.registry.scheduler = scheduler
    # scheduler.remove_all_jobs()
    # scheduler.start()
    resync_all_job = scheduler.get_job('resync_all')
    now = datetime.now(TZ)
    if not resync_all_job or resync_all_job.next_run_time < now - timedelta(hours=1):
        if resync_all_job:
            args = resync_all_job.args
        else:
            args = [settings.get('callback.url') + 'resync_all', None]
        run_date = now + timedelta(seconds=60)
        scheduler.add_job(push, 'date', run_date=run_date, timezone=TZ,
                          id='resync_all', args=args,
                          replace_existing=True, misfire_grace_time=60 * 60)
    return config.make_wsgi_app()
