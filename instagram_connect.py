from dependencies import bottle
from dependencies.bottle import route, request
from dependencies.instagram import client
from dependencies.workflow import Workflow
import os
import sys

account_type = sys.argv[1]

_wf = None

def wf():
    global _wf
    if _wf is None:
        _wf = Workflow()
    return _wf
    
    
bottle.debug(True)

app = bottle.app()

CONFIG = {
    'client_id': '6104a3c347304a54909d5dc8b7253c36',
    'client_secret': '16cf9a1467b740d295631397e17512e5',
    'redirect_uri': 'http://localhost:8515/oauth_callback'
}

unauthenticated_api = client.InstagramAPI(**CONFIG)

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
    except Exception as e:
        print(e)
        return e
    else:
        if not access_token:
            return 'Could not get access token'
        api = client.InstagramAPI(access_token=access_token, 
                            client_secret=CONFIG['client_secret'])
        settings = wf().settings
        if account_type == 'primary':
            access_dict = dict([('primary_access_token', access_token)])
            settings.update(access_dict)
        elif account_type == 'secondary':
            secondary_access_tokens = settings.get('secondary_access_tokens', None)
            if not secondary_access_tokens:
                access_dict = {'secondary_access_tokens': [access_token]}
                settings.update(access_dict)
            else:
                # Already exists secondary access tokens
                # Check if the access token already exists
                if access_token in secondary_access_tokens:
                    return ('<p>Already configured this account</p>')
                else:
                    secondary_access_tokens.append(access_token)
                    settings.update( {'secondary_access_tokens': secondary_access_tokens} )
        return ('<p>Successfully connected app<br />' +
                'Access Token: {}</p>'.format(access_token) )
    
bottle.run(app=app, host='localhost', port=8515, reloader=True)