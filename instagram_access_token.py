import dependencies.bottle
import beaker.middleware
from dependencies.bottle import route, redirect, post, run, request, hook
from dependencies.instagram import client

bottle.debug(True)

session_opts = {
    'session.type': 'file',
    'session.data_dir': './session/',
    'session.auto': True,
}

app = beaker.middleware.SessionMiddleware(bottle.app(), session_opts)

CONFIG = {
    'client_id': '6104a3c347304a54909d5dc8b7253c36',
    'client_secret': '16cf9a1467b740d295631397e17512e5',
    'redirect_uri': 'http://localhost:8515/oauth_callback'
}

unauthenticated_api = client.InstagramAPI(**CONFIG)

@hook('before_request')
def setup_request():
    request.session = request.environ['beaker.session']


@route('/')
def home():
    try:
        url = unauthenticated_api.get_authorize_url()
        return '<a href="%s">Connect with Instagram</a>' % url
    except Exception as e:
        print(e)
        
@route('/oauth_callback')
def on_callback():
    code = request.GET.get("code")
    if not code:
        return 'Missing code'
    try:
        access_token, user_info = unauthenticated_api.exchange_code_for_access_token(code)
        if not access_token:
            return 'Could not get access token'
        api = client.InstagramAPI(access_token=access_token, client_secret=CONFIG['client_secret'])
        request.session['access_token'] = access_token
    except Exception as e:
        print(e)
    return 'Successfully connected app'
    
bottle.run(app=app, host='localhost', port=8515, reloader=True)