from dependencies.workflow import Workflow
from dependencies.workflow import background
from grammie import AlfredItems
from dependencies.instagram.client import InstagramAPI
import sys

# Commands for actioning items
CHANGE_PRIMARY = 0
MAKE_PRIMARY = 1
NEW_ACCOUNT = 2
REMOVE_ACCOUNT = 3
NEW_PRIMARY_FROM_SECONDARY = 4
REMOVE_PRIMARY = 5
REMOVE_SECONDARY = 6
NEW_PRIMARY = 7
# String value of commands (for debugging)
COMMANDS = ['Change_primary', 'Make_primary', 'New_account',
            'Remove_account', 'New_primary_from_secondary',
            'Remove_primary', 'Remove_secondary', 'New_primary']

FROM_CACHE = 0  # 0 means load wf.cached_data directly from cache

# Instagram API configuration
CONFIG = {
    'client_id': '6104a3c347304a54909d5dc8b7253c36',
    'client_secret': '16cf9a1467b740d295631397e17512e5',
    'redirect_uri': 'http://localhost:8515/oauth_callback'
}

# Initialize workflow instance
_wf = None
def wf():
    global _wf
    if _wf is None:
        _wf = Workflow()
    return _wf

######################################################################
########################## Main Function #############################
######################################################################

def main(wf):
    """Configure options and access tokens for the Instastalk workflow"""
    
    
    # Get query passed from alfred
    query = wf.args[0]
    # An empty query means the script is being run for the first time
    if query == '':
        wf.alfred_items = AlfredItems(wf, name='configure_special_info')
        # Check if the settings file exists
        settings = wf.settings
        if not settings:
            configure_initial()
        else:
            configure_main()
    
    # Otherwise find the previously selected item from query
    else:
        firstchar = query[0]
        # Default values for command and data
        command = None
        data = None
        unival = ord(firstchar)
        if unival in AlfredItems.non_printing_univals():
            # Found a special character key from autocomplete of previous script
            info = wf.cached_data('configure_special_info', max_age=FROM_CACHE)
            # Get the selected command and associated data from previously run script
            #  'info' contains a list of all options to select from previous script
            #  'unival' is the ordinal of the unicode character passed from autocompleting
            #     the actionied item from previous script
            command, data = info[unival]
            # # Cache value to exclude it from next time script is run. Alfred will not rerun the script if the autocomplete value is the same as before
            # wf.cache_data('unival',unival)
            log.debug('Received special unicode value, command: {command}'.format(command=COMMANDS[command]))
            
            # Initialize generators for special info
            # First find previously chosen unival to exclude it from new range
            previous_unival = unival
            wf.alfred_items = AlfredItems(wf, previous_unival, name='configure_special_info')
            # Send previous info to alfred_items in case user accesses the previous information in alfred by scrolling
            wf.alfred_items.special_info.send({previous_unival: (command, data)})
        else:
            wf.alfred_items = AlfredItems(wf, name='configure_special_info')

        # Execute navigtion function appropriate to the command
        if command == CHANGE_PRIMARY:
            change_primary()
        elif command == MAKE_PRIMARY:
            new_primary_token = data
            exchange_primary_and_secondary_tokens(new_primary_token)
            configure_main()
        elif command == NEW_ACCOUNT:
            associate_instagram_account('secondary')
        elif command == REMOVE_ACCOUNT:
            remove_account()
        elif command == NEW_PRIMARY_FROM_SECONDARY:
            new_primary_from_secondary()
        elif command == REMOVE_PRIMARY:
            remove_primary()
        elif command == REMOVE_SECONDARY:
            secondary_token = data
            remove_secondary(secondary_token)
        elif command == NEW_PRIMARY:
            secondary_token = data
            new_primary(secondary_token)
    # Write the item data to a file so the item the user selected determines how the script is run next
    wf.alfred_items.special_info.close()
    # Send XML formatted result to Alred
    wf.send_feedback()

                
    # Look for a previously selected alfred item


######################################################################
####################### Initial Configuration ########################
######################################################################

def configure_initial():
    pass

######################################################################
###################### Continued Configuration #######################
######################################################################

def configure_main():
    """Configure workflow after settings already exist"""
    # Add item to change primary account
    settings = wf().settings
    primary_account = settings.get('primary_access_token', None)
    secondary_accounts = settings.get('secondary_access_tokens', [])
    if primary_account:
        if len(secondary_accounts):
            total_accounts = len(secondary_accounts) + 1
            special_unicode_value = prepare_item_with_command(CHANGE_PRIMARY)
            wf().add_item( title='Change primary account',
                         subtitle='Total registered accounts: {accounts}'.format(accounts=total_accounts),
                         valid=False,
                         autocomplete=unichr(special_unicode_value)
                       )

        # Add item to associate a new instagram account
        special_unicode_value = prepare_item_with_command(NEW_ACCOUNT)
        wf().add_item( title='Add a new secondary account',
                     subtitle='Gain access to info of users if private and followed by your account',
                     valid=False,
                     autocomplete=unichr(special_unicode_value)
                   )

        # Add item to remove an account
        special_unicode_value = prepare_item_with_command(REMOVE_ACCOUNT)
        wf().add_item( title='Remove an account',
                       valid=False,
                       autocomplete=unichr(special_unicode_value)
                     )
        
    else:
        # No primary account exists, need to make one
        associate_instagram_account('primary')


######################################################################
####################### Navigation Functions #########################
######################################################################

def change_primary():
    """Change the primary account"""
    # Get the accounts already associated with the workflow
    primary_access_token = wf().settings.get('primary_access_token', None)
    secondary_access_tokens = wf().settings.get('secondary_access_tokens', [])
    # If a primary doesn't exist, need to make one
    if not primary_access_token:
        associate_instagram_account('primary')
    else:
        # Otherwise make items for each account
        primary_api = InstagramAPI(access_token=primary_access_token, client_secret=CONFIG['client_secret'])
        primary_user = primary_api.user('self')
        special_unicode_value = prepare_item_with_command(MAKE_PRIMARY, primary_access_token)
        wf().add_item( title='User: {user} (Currently Primary)'.format(user=primary_user.username),
                       subtitle='Keep as primary',
                       valid=False,
                       autocomplete=unichr(special_unicode_value)
                     )
        # Make items for secondary accounts
        for secondary in secondary_access_tokens:
            secondary_api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=secondary)
            secondary_user = secondary_api.user('self')
            special_unicode_value = prepare_item_with_command(MAKE_PRIMARY, secondary)
            wf().add_item( title='User: {user}'.format(user=secondary_user.username),
                           subtitle='Make primary',
                           valid=False,
                           autocomplete=unichr(special_unicode_value)
                         )

def remove_account():
    """List all accounts registered to remove one of them"""
    # Get the accounts already associated with the workflow
    primary_access_token = wf().settings.get('primary_access_token', None)
    secondary_access_tokens = wf().settings.get('secondary_access_tokens', [])
    num_secondary_accounts = len(secondary_access_tokens)
    
    # First list the primary account
    primary_api = InstagramAPI(access_token=primary_access_token, client_secret=CONFIG['client_secret'])
    primary_user = primary_api.user('self')
    if num_secondary_accounts > 0:
        special_unicode_value = prepare_item_with_command(NEW_PRIMARY_FROM_SECONDARY)
        subtitle = 'You will be prompted to select a new primary account'
    else:
        special_unicode_value = prepare_item_with_command(REMOVE_PRIMARY)
        subtitle = 'Warning: you won\'t have any Instagram accounts if you remove this one'
    wf().add_item( title='Remove {user} (primary)'.format(user=primary_user.username),
                   subtitle=subtitle,
                   valid=False,
                   autocomplete=unichr(special_unicode_value)
                 )

    # List all of the secondary accounts
    for secondary_token in secondary_access_tokens:
        secondary_api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=secondary_token)
        secondary_user = secondary_api.user('self')
        special_unicode_value = prepare_item_with_command(REMOVE_SECONDARY, secondary_token)
        wf().add_item( title='Remove {user}'.format(user=secondary_user.username),
                       valid=False,
                       autocomplete=unichr(special_unicode_value)
                     )

def new_primary_from_secondary():
    """Make a secondary account primary, remove primary account"""
    # List all secondary accounts
    secondary_access_tokens = wf().settings.get('secondary_access_tokens', [])
    for secondary_token in secondary_access_tokens:
        secondary_api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=secondary_token)
        secondary_user = secondary_api.user('self')
        special_unicode_value = prepare_item_with_command(NEW_PRIMARY, secondary_token)
        wf().add_item( title='Make {user} the primary user'.format(user=secondary_user.username),
                       subtitle='Removes current primary account',
                       valid=False,
                       autocomplete=unichr(special_unicode_value)
                     )

def remove_primary():
    """Delete the primary account"""
    token = wf().settings.pop('primary_access_token')
    wf().settings.save()
    api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=token)
    user = api.user('self')
    wf().add_item( title='Removed {user}'.format(user=user.username) )

def remove_secondary(secondary_token):
    """Delete a secondary account"""
    wf().settings['secondary_access_tokens'].remove(secondary_token)
    wf().settings.save()
    api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=secondary_token)
    user = api.user('self')
    wf().add_item( title='Removed {user}'.format(user=user.username) )

def new_primary(secondary_token):
    """Make a secondary account the primary account, deleting the primary token"""
    old_primary_token = wf().settings['primary_access_token']
    old_primary_api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=old_primary_token)
    old_primary = old_primary_api.user('self')
    wf().settings['primary_access_token'] = secondary_token
    wf().settings['secondary_access_tokens'].remove(secondary_token)
    api = InstagramAPI(client_secret=CONFIG['client_secret'], access_token=secondary_token)
    user = api.user('self')
    wf().add_item( title='Removed {old_primary}, made {new_primary} primary'.format(
                        old_primary=old_primary.username, new_primary=user.username)
                 )
######################################################################
######################## Helper functions ############################
######################################################################

def prepare_item_with_command(command, data=None):
    """Prepare an alfred item with information needed to action a command"""
    special_unicode_value = wf().alfred_items.special_unicode_value.next()
    special_info = {special_unicode_value: (command, data)}
    wf().alfred_items.special_info.send(special_info)
    return special_unicode_value

def associate_instagram_account(account_type):
    """Get permission from user to associate their instrgram account"""
    # Start a subprocess to load a webpage to get instagram permission
    unauthorized_api = InstagramAPI(**CONFIG)
    scope = ['comments', 'likes', 'relationships']
    authorize_url = unauthorized_api.get_authorize_url(scope=None)
    args = ['/usr/bin/python', wf().workflowfile('instagram_connect.py'), account_type]
    # if background.is_running('connect'):
    #     log.debug('Process `connect` is already running')
    # else:
    background.run_in_background('connect', args, timeout=120)
                              
    wf().add_item( title='Connect your instagram account', 
                   valid=True,
                   arg=authorize_url)

def exchange_primary_and_secondary_tokens(new_primary_token):
    """Exchange the primary and secondary tokens, making the secondary primary"""
    # Switch primary and secondary accounts
    old_primary_token = wf().settings['primary_access_token']
    secondary_access_tokens = wf().settings['secondary_access_tokens']
    # Make the access_token in 'data' the new primary
    wf().settings['primary_access_token'] = new_primary_token
    # Remove new primary token from secondary
    try:
        secondary_access_tokens.remove(new_primary_token)
    except ValueError as err:
        # Access token not in secondary, probably was the primary token
        pass
    else:
        # Add old primary token to secondary
        secondary_access_tokens.append(old_primary_token)
        wf().settings['secondary_access_tokens'] = secondary_access_tokens

######################## End of functions ############################

if __name__ == '__main__':
    log = wf().logger
    sys.exit(wf().run(main))